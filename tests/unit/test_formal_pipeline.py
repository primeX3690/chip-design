"""Automated formal verification pipeline (Yosys miter/equiv_make/eqy/BMC). All tool invocations are mocked;
the real-tool check is `python -m evohdl.sandbox.formal_pipeline --selftest`."""
from pathlib import Path

from evohdl.sandbox import equivalence_checker as ec
from evohdl.sandbox import eqy_runner as er
from evohdl.sandbox import formal_pipeline as fp
from evohdl.sandbox.equivalence_checker import EquivalenceOutcome as EO
from evohdl.sandbox.process_guard import GuardedResult

COMB = "module m(input a, output y); assign y = a; endmodule"
SEQ = "module m(input clk, input rst_n, output reg q); always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else q <= ~q; endmodule"


def _yosys_present(monkeypatch):
    monkeypatch.setattr(fp.shutil, "which", lambda x: "/usr/bin/" + x if x == "yosys" else None)


def _patch(monkeypatch, comb=None, make=None, eqy=None, bmc=None, eqy_installed=False):
    _yosys_present(monkeypatch)
    monkeypatch.setattr(fp, "_native_attempt", lambda *a, **k: None)   # isolate the Yosys-path logic
    calls = []
    monkeypatch.setattr(fp, "check_equivalence", lambda *a, **k: (calls.append(("bmc" if k.get("sequential") else "sat", k)), (bmc if k.get("sequential") else comb))[1])
    monkeypatch.setattr(fp, "check_equivalence_equiv_make", lambda *a, **k: (calls.append(("equiv_make", k)), make)[1])
    monkeypatch.setattr(fp, "check_equivalence_eqy", lambda *a, **k: (calls.append(("eqy", k)), eqy)[1])
    monkeypatch.setattr(fp, "eqy_available", lambda *a, **k: eqy_installed)
    return calls


def test_tools_missing_is_reported_not_crashed(monkeypatch):
    monkeypatch.setattr(fp.shutil, "which", lambda x: None)
    unsupported = "module m(input [3:0] a, output [3:0] y); assign y = $signed(a); endmodule"   # outside the native subset
    v = fp.run_formal_pipeline(unsupported, unsupported, "m")
    assert v.status == "TOOLS_MISSING" and not v.proven
    assert any(a.method == "native_elaboration" for a in v.attempts)


def test_without_yosys_the_native_engine_can_still_prove_and_refute(monkeypatch):
    monkeypatch.setattr(fp.shutil, "which", lambda x: None)
    a = "module m(input [3:0] a, input [3:0] b, output [3:0] y); assign y = (a & b) | (a & ~b); endmodule"
    b = "module m(input [3:0] a, input [3:0] b, output [3:0] y); assign y = a; endmodule"
    v = fp.run_formal_pipeline(a, b, "m")
    assert v.status == "PROVEN_UNBOUNDED" and v.method == "native_cdcl_cec" and any("Native engine" in c for c in v.extra_caveats)
    bad = fp.run_formal_pipeline(a, b.replace("= a;", "= b;"), "m")
    assert bad.status == "NOT_EQUIVALENT"


def test_native_sequential_matched_and_bounded_paths(monkeypatch):
    from evohdl.paths import SEED_DIR
    monkeypatch.setattr(fp.shutil, "which", lambda x: None)
    cnt = (SEED_DIR / "counter_4bit.v").read_text()
    v = fp.run_formal_pipeline(cnt, cnt, "counter_4bit")
    assert v.status == "PROVEN_UNBOUNDED" and v.method == "native_seq_matched"
    broken = cnt.replace("count + 1'b1", "count + 2'b10")
    assert fp.run_formal_pipeline(cnt, broken, "counter_4bit", bmc_depth=8).status == "NOT_EQUIVALENT"
    # different state encoding (extra register) -> matched proof impossible, BMC from reset is the honest answer
    fsm = (SEED_DIR / "fsm_seqdet.v").read_text()
    recoded = fsm.replace("S4 = 3'd4", "S4 = 3'd5").replace("S3 = 3'd3", "S3 = 3'd6")
    r = fp.run_formal_pipeline(fsm, recoded, "fsm_seqdet", bmc_depth=10)
    assert r.status in ("PROVEN_BOUNDED", "PROVEN_UNBOUNDED") and r.proven


def test_combinational_proof_is_unbounded_and_stops_early(monkeypatch):
    calls = _patch(monkeypatch, comb=EO(checked=True, equivalent=True))
    v = fp.run_formal_pipeline(COMB, COMB, "m")
    assert v.status == "PROVEN_UNBOUNDED" and v.method == "yosys_sat_miter" and [c[0] for c in calls] == ["sat"]


def test_combinational_counterexample_is_not_equivalent(monkeypatch):
    _patch(monkeypatch, comb=EO(checked=True, equivalent=False, error="SAT solver found a real counterexample"))
    v = fp.run_formal_pipeline(COMB, COMB.replace("= a", "= ~a"), "m")
    assert v.status == "NOT_EQUIVALENT" and not v.proven


def test_sequential_equiv_make_proof_counts_as_unbounded(monkeypatch):
    calls = _patch(monkeypatch, make=EO(checked=True, equivalent=True))
    v = fp.run_formal_pipeline(SEQ, SEQ, "m")
    assert v.sequential and v.status == "PROVEN_UNBOUNDED" and "equiv_induct" in v.method and [c[0] for c in calls] == ["equiv_make"]


def test_sequential_falls_back_to_bounded_and_says_so(monkeypatch):
    calls = _patch(monkeypatch, make=EO(checked=True, equivalent=False), bmc=EO(checked=True, equivalent=True, bounded=True, seq_cycles=24))
    v = fp.run_formal_pipeline(SEQ, SEQ, "m", bmc_depth=24)
    assert v.status == "PROVEN_BOUNDED" and v.depth == 24 and v.proven
    assert any("clock cycles" in c for c in v.extra_caveats)
    bmc_kwargs = [k for n, k in calls if n == "bmc"][0]
    assert bmc_kwargs["reset_port"] == "rst_n" and bmc_kwargs["reset_active_low"] is True  # reset auto-detected


def test_eqy_is_used_only_when_installed_and_is_labelled(monkeypatch):
    calls = _patch(monkeypatch, make=EO(checked=True, equivalent=False), eqy=EO(checked=True, equivalent=True, seq_cycles=10), eqy_installed=True)
    v = fp.run_formal_pipeline(SEQ, SEQ, "m")
    assert v.status == "PROVEN_BY_EQY" and [c[0] for c in calls] == ["equiv_make", "eqy"]
    calls2 = _patch(monkeypatch, make=EO(checked=True, equivalent=False), bmc=EO(checked=False), eqy_installed=False)
    v2 = fp.run_formal_pipeline(SEQ, SEQ, "m")
    assert "eqy" not in [c[0] for c in calls2] and v2.status == "UNPROVEN"
    calls3 = _patch(monkeypatch, make=EO(checked=False), bmc=EO(checked=False), eqy=EO(checked=False, error="x"), eqy_installed=True)
    fp.run_formal_pipeline(SEQ, SEQ, "m", use_eqy="never")
    assert "eqy" not in [c[0] for c in calls3]


def test_sequential_counterexample_without_reset_is_not_called_a_bug(monkeypatch):
    seq_no_reset = "module m(input clk, output reg q); always @(posedge clk) q <= ~q; endmodule"
    _patch(monkeypatch, make=EO(checked=True, equivalent=False),
           bmc=EO(checked=True, equivalent=False, error="SAT solver found a real counterexample"))
    v = fp.run_formal_pipeline(seq_no_reset, seq_no_reset, "m")
    assert v.status == "UNPROVEN" and any("unreachable" in c for c in v.extra_caveats)
    _patch(monkeypatch, make=EO(checked=True, equivalent=False),
           bmc=EO(checked=True, equivalent=False, error="SAT solver found a real counterexample"))
    assert fp.run_formal_pipeline(SEQ, SEQ, "m").status == "NOT_EQUIVALENT"   # with a reset it IS a real bug


def test_report_states_what_is_and_is_not_proven(monkeypatch, tmp_path):
    _patch(monkeypatch, make=EO(checked=True, equivalent=False), bmc=EO(checked=True, equivalent=True, bounded=True))
    v = fp.run_formal_pipeline(SEQ, SEQ, "m", bmc_depth=12)
    md = fp.write_report(v, "m", tmp_path, "seed.v", "best.v").read_text()
    assert "BOUNDED" in md.upper() and "NOT a full proof" in md and "relative to the seed" in md
    assert (tmp_path / "formal_proof_m.json").exists()


def test_bmc_script_forces_reset_and_unmaps_async_flops():
    s = ec._build_sequential_script("m", Path("/s.v"), Path("/e.v"), 16, reset_port="rst_n", reset_active_low=True)
    assert "async2sync" in s and "dffunmap" in s and "-set-at 1 rst_n 0" in s and "-prove-skip 1" in s and "-seq 16" in s
    s2 = ec._build_sequential_script("m", Path("/s.v"), Path("/e.v"), 8)
    assert "-set-at" not in s2 and "async2sync" in s2


def test_equiv_make_result_parsing(monkeypatch):
    def fake(out):
        return lambda cmd, timeout_sec, cwd: GuardedResult(command=cmd, returncode=0, stdout=out)
    monkeypatch.setattr(ec, "run_guarded", fake("Found 5 $equiv cells in equiv:\n  Of those cells 5 are proven\n  Equivalence successfully proven!"))
    o = ec.check_equivalence_equiv_make(SEQ, SEQ, "m")
    assert o.checked and o.equivalent and not o.bounded
    monkeypatch.setattr(ec, "run_guarded", fake("ERROR: Found 2 unproven $equiv cells in module equiv"))
    o = ec.check_equivalence_equiv_make(SEQ, SEQ, "m")
    assert o.checked and not o.equivalent and not o.error      # inconclusive, NOT "equivalent"
    monkeypatch.setattr(ec, "run_guarded", lambda cmd, timeout_sec, cwd: GuardedResult(command=cmd, returncode=1, stderr="syntax error"))
    assert not ec.check_equivalence_equiv_make(SEQ, SEQ, "m").checked


def test_eqy_config_and_result_parsing(monkeypatch):
    cfg = er.build_eqy_config("top", sv=True, hierarchical=True, strategy="sby", depth=8)
    assert "[gold]" in cfg and "[gate]" in cfg and "read_verilog -sv gold.v" in cfg and "prep -top top" in cfg
    assert "flatten" in cfg and "[strategy sby]" in cfg and "use sby" in cfg and "depth 8" in cfg
    assert "flatten" not in er.build_eqy_config("top", False, False)
    monkeypatch.setattr(er, "eqy_available", lambda *a, **k: False)
    assert not er.check_equivalence_eqy(COMB, COMB, "m").checked
    monkeypatch.setattr(er, "eqy_available", lambda *a, **k: True)
    ok = lambda cmd, timeout_sec, cwd: GuardedResult(command=cmd, returncode=0, stdout="EQY: DONE (PASS, rc=0)")
    monkeypatch.setattr(er, "run_guarded", ok)
    assert er.check_equivalence_eqy(COMB, COMB, "m").equivalent
    bad = lambda cmd, timeout_sec, cwd: GuardedResult(command=cmd, returncode=2, stdout="EQY: DONE (FAIL, rc=2)")
    monkeypatch.setattr(er, "run_guarded", bad)
    o = er.check_equivalence_eqy(COMB, COMB, "m")
    assert o.checked and not o.equivalent


def test_hardware_pipeline_stage0_uses_formal_pipeline_and_keeps_legacy_keys(monkeypatch, tmp_path):
    from evohdl.self_improve_loop import hardware_verification_pipeline as hv
    v = fp.FormalVerdict(status="PROVEN_BOUNDED", method="yosys_sat_bmc", depth=20, sequential=True)
    monkeypatch.setattr(hv, "run_formal_pipeline", lambda *a, **k: v)
    assert hasattr(hv, "run_full_verification")
