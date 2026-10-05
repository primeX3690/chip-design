"""Head-to-head harness: script generation, output parsing, verified-prepass round trip, verdict logic (Yosys mocked)."""
import csv
import json
import random
from pathlib import Path

from evohdl.eda import compare as C
from evohdl.eda.aig_verilog import aig_to_verilog, module_ports
from evohdl.eda.cec import combinational_equiv
from evohdl.eda.elaborate import elaborate
from evohdl.eda.opt import optimize
from evohdl.paths import REPO_ROOT
from evohdl.sandbox.design_bundle import load_design_bundle
from evohdl.sandbox.formal_pipeline import FormalVerdict
from evohdl.sandbox.process_guard import GuardedResult

SUITE = json.loads((REPO_ROOT / "benchmarks" / "suite.json").read_text())["benchmarks"]


def _src(name):
    b = next(x for x in SUITE if x["name"] == name)
    return load_design_bundle(b["files"], top=b["top"], root=REPO_ROOT).source, b["top"]


def test_script_generation_for_all_targets():
    p = Path("/x/design.v")
    s = C.build_yosys_script(p, "top", "/l.lib", "default", "asic", False, False, [])
    assert "synth -top top -flatten" in s and "abc -liberty /l.lib" in s and "-script" not in s and "dfflibmap" not in s
    assert "stat -liberty /l.lib" in s and "ltp -noff" in s
    s2 = C.build_yosys_script(p, "top", "/l.lib", "area_strong", "asic", True, True, ["*_1", "*bufz*"])
    assert "dfflibmap -liberty /l.lib" in s2 and "-script +strash;dc2;dc2;dch -f;map -a" in s2
    assert "-dont_use *_1" in s2 and "-dont_use *bufz*" in s2 and "read_verilog -sv" in s2
    s3 = C.build_yosys_script(p, "top", None, "default", "ice40", False, False, [])
    assert "synth_ice40 -top top -flatten" in s3 and "liberty" not in s3


def test_parsing_old_and_new_yosys_formats():
    old = "=== t ===\n   Number of cells:   120\n   Chip area for module '\\t': 345.600000\n\nLongest topological path in t (length=9):\n"
    r = C.parse_yosys_output(old, "asic")
    assert r.ok and r.cells == 120 and abs(r.area - 345.6) < 1e-9 and r.depth == 9
    new = "=== t ===\n\n      200 cells\n   Chip area for top module '\\t': 99.5\n"
    r = C.parse_yosys_output(new, "asic")
    assert r.ok and r.cells == 200 and r.area == 99.5
    assert not C.parse_yosys_output("   Number of cells: 5\n", "asic").ok       # no area line -> explicit failure, not 0
    assert not C.parse_yosys_output("garbage", "asic").ok
    ice = "      150 cells\n      SB_LUT4   97\n      SB_CARRY  4\n"
    r = C.parse_yosys_output(ice, "ice40")
    assert r.ok and r.area == 97.0
    ice_new = "        150 cells\n         97   SB_LUT4\n"
    assert C.parse_yosys_output(ice_new, "ice40").area == 97.0


def test_prepass_verilog_keeps_interface_and_is_equivalent_on_every_native_combinational_benchmark():
    checked = 0
    for b in SUITE:
        src, top = _src(b["name"])
        try:
            g = elaborate(src, top)
        except Exception:
            continue
        if g.latches:
            continue
        o = optimize(g.cleanup(), effort=1)
        ports = module_ports(src, top)
        v = aig_to_verilog(o, top, ports)
        assert module_ports(v, top) == ports, b["name"]              # identical port names/order/widths
        assert combinational_equiv(o, elaborate(v, top)).equivalent, b["name"]
        assert combinational_equiv(g, o).equivalent, b["name"]
        checked += 1
    assert checked >= 12
    try:
        aig_to_verilog(elaborate(*_src("counter_4bit")), "counter_4bit", module_ports(*_src("counter_4bit")))
    except ValueError as e:
        assert "combinational" in str(e)
    else:
        raise AssertionError("sequential AIG must be refused")


def test_rtl_suite_implements_what_it_claims():
    def run(name, **vals):
        src, top = _src(name)
        g = elaborate(src, top)
        inp = {}
        for k, (v, w) in vals.items():
            for i in range(w):
                inp[k if w == 1 else f"{k}[{i}]"] = (v >> i) & 1
        return g.simulate(inp)[0]

    def pack(o, n, w):
        return sum(o[n if w == 1 else f"{n}[{i}]"] << i for i in range(w))
    rng = random.Random(3)
    for _ in range(60):
        r, x, a, b, d, s, k = (rng.getrandbits(16), rng.getrandbits(16), rng.getrandbits(16), rng.getrandbits(16),
                               rng.getrandbits(32), rng.randrange(32), rng.randrange(16))
        o = run("prio16", r=(r, 16))
        assert o["valid"] == int(r > 0) and (r == 0 or pack(o, "idx", 4) == r.bit_length() - 1)
        assert pack(run("popcnt16", x=(x, 16)), "c", 5) == bin(x).count("1")
        o = run("cmp16", a=(a, 16), b=(b, 16))
        assert (o["eq"], o["lt"], o["gt"]) == (int(a == b), int(a < b), int(a > b))
        assert run("mux32", d=(d, 32), s=(s, 5))["y"] == (d >> s) & 1
        assert pack(run("shift16", x=(x, 16), k=(k, 4)), "y", 16) == (x << k) & 0xFFFF
        assert pack(run("mul8", a=(a & 255, 8), b=(b & 255, 8)), "p", 16) == (a & 255) * (b & 255)
        assert pack(run("add16", a=(a, 16), b=(b, 16)), "s", 17) == a + b
        assert run("parity32", x=(d, 32))["p"] == bin(d).count("1") & 1
        pa, pb = [rng.randrange(64) for _ in range(4)], [rng.randrange(64) for _ in range(4)]
        vals = {f"a{i}": (pa[i], 6) for i in range(4)} | {f"b{i}": (pb[i], 6) for i in range(4)}
        assert pack(run("sad4", **vals), "sad", 8) == sum(abs(x - y) for x, y in zip(pa, pb))


def _mock_yosys(monkeypatch, base_area=1000.0, pre_area=900.0, formal="PROVEN_UNBOUNDED"):
    monkeypatch.setattr(C.shutil, "which", lambda x: "/usr/bin/yosys" if x == "yosys" else None)
    monkeypatch.setattr(C, "tool_version", lambda *a, **k: "Yosys 0.99 (mock)")

    def fake(cmd, timeout_sec, cwd):
        script = Path(cmd[cmd.index("-s") + 1]).read_text()
        design = Path(next(l.split()[-1] for l in script.splitlines() if l.startswith("read_verilog"))).read_text()
        area = pre_area if "wire _n" in design else base_area
        return GuardedResult(command=cmd, returncode=0, stdout=f"   Number of cells: 50\n   Chip area for module '\\t': {area}\nLongest topological path in t (length=7):\n")
    monkeypatch.setattr(C, "run_guarded", fake)
    monkeypatch.setattr(C, "run_formal_pipeline", lambda *a, **k: FormalVerdict(status=formal, method="mock"))


def _suite(tmp_path, names):
    p = tmp_path / "suite.json"
    p.write_text(json.dumps({"benchmarks": [b for b in SUITE if b["name"] in names]}))
    return p


def test_wins_ties_losses_and_report_content(monkeypatch, tmp_path):
    _mock_yosys(monkeypatch, 1000.0, 900.0)
    res = C.run_suite(_suite(tmp_path, ["comparator_4bit", "cmp16"]), None, tmp_path / "o", flavors=["default"], effort=1)
    s = res["summary"]["default"]
    assert s["compared"] == 2 and len(s["wins"]) == 2 and abs(s["geomean_area_ratio"] - 0.9) < 1e-9
    md = Path(res["report"]).read_text()
    assert "-10.0%" in md and "ILLUSTRATIVE" in md and "What this report does NOT show" in md and "Yosys 0.99 (mock)" in md
    rows = list(csv.DictReader(open(tmp_path / "o" / "results.csv")))
    assert rows[0]["delta_pct"] == "-10.0" and rows[0]["verified"] == "True"
    assert (tmp_path / "o" / "prepass" / "cmp16.v").exists() and json.loads((tmp_path / "o" / "results.json").read_text())["meta"]["have_yosys"]

    _mock_yosys(monkeypatch, 1000.0, 1100.0)                       # worse -> must be reported as a loss, never hidden
    res = C.run_suite(_suite(tmp_path, ["cmp16"]), None, tmp_path / "o2", flavors=["default"], effort=1)
    assert res["summary"]["default"]["losses"] == ["cmp16"] and "+10.0%" in Path(res["report"]).read_text()

    _mock_yosys(monkeypatch, 1000.0, 1000.0)                       # tie and the "no wins" warning
    res = C.run_suite(_suite(tmp_path, ["cmp16"]), None, tmp_path / "o3", flavors=["default"], effort=1)
    assert res["summary"]["default"]["ties"] == ["cmp16"]
    assert "No wins were found" in Path(res["report"]).read_text()


def test_unverified_prepass_is_never_counted_as_a_win(monkeypatch, tmp_path):
    _mock_yosys(monkeypatch, 1000.0, 500.0, formal="NOT_EQUIVALENT")
    res = C.run_suite(_suite(tmp_path, ["cmp16"]), None, tmp_path / "o", flavors=["default"], effort=1)
    s = res["summary"]["default"]
    assert s["compared"] == 0 and s["wins"] == [] and s["skipped"] == ["cmp16"]


def test_unsupported_and_sequential_designs_are_reported_honestly(monkeypatch, tmp_path):
    _mock_yosys(monkeypatch)
    res = C.run_suite(_suite(tmp_path, ["picorv32_alu", "fsm_seqdet"]), None, tmp_path / "o", flavors=["default"], effort=1)
    rows = {r["name"]: r for r in res["rows"]}
    assert rows["picorv32_alu"]["native"]["supported"] is False and rows["picorv32_alu"]["prepass"]["applicable"] is False
    assert rows["fsm_seqdet"]["sequential"] and "sequential" in rows["fsm_seqdet"]["prepass"]["reason"]
    assert rows["fsm_seqdet"]["baseline"]["default"]["ok"]           # the Yosys baseline still ran for both
    md = Path(res["report"]).read_text()
    assert "pre-pass n/a" in md


def test_without_yosys_the_report_says_no_head_to_head_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(C.shutil, "which", lambda x: None)
    res = C.run_suite(_suite(tmp_path, ["cmp16"]), None, tmp_path / "o", flavors=["default"], effort=1)
    md = Path(res["report"]).read_text()
    assert "NO head-to-head result exists" in md and res["summary"]["default"]["compared"] == 0
    assert res["rows"][0]["prepass"]["verify_native_cec"] == "EQUIVALENT"        # native verification still runs
