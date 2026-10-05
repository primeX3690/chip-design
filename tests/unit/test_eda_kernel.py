"""Native EDA kernel (evohdl.eda): AIG, CDCL SAT, CEC/BMC, elaboration, optimizer, Liberty, tech mapping, STA, power,
benchmark I/O, regression DB, CLI. Everything runs in pure Python -- no Yosys/Verilator needed."""
import itertools
import random

from evohdl.eda import aig as A
from evohdl.eda import benchmarks as B
from evohdl.eda.bench_io import read_aag, read_bench, write_aag, write_bench
from evohdl.eda.cec import bmc_equiv, combinational_equiv, sequential_equiv_matched
from evohdl.eda.cli import main as cli_main
from evohdl.eda.elaborate import elaborate
from evohdl.eda.flow import run_flow, verify, sim_check
from evohdl.eda.liberty import load_liberty, parse_liberty
from evohdl.eda.netlist import Netlist
from evohdl.eda.opt import balance, fraig, optimize, rewrite
from evohdl.eda.regress import connect, find_regressions, record
from evohdl.eda.sat import solve, _luby
from evohdl.eda.sta import Constraints, analyze, estimate_power, parse_sdc
from evohdl.eda.techmap import techmap
from evohdl.hdl.ast_nodes import PortDecl
from evohdl.hdl.parser import parse_source
from evohdl.hdl.pysim import PySim, Widths
from evohdl.paths import DESIGNS_DIR, REPO_ROOT, SEED_DIR

LIB = load_liberty(REPO_ROOT / "libs" / "tiny_generic.lib")


# ---------------------------------------------------------------- AIG + SAT
def test_aig_simplifications_and_simulation():
    g = A.Aig()
    p, q = g.new_input("p"), g.new_input("q")
    t = g.AND(p, q)
    assert g.AND(t, p) == t and g.AND(t, p ^ 1) == 0 and g.AND(t ^ 1, p ^ 1) == (p ^ 1) and g.AND(p, p ^ 1) == 0
    g.add_output("x", g.XOR(p, q))
    for a, b in itertools.product([0, 1], repeat=2):
        assert g.simulate({"p": a, "q": b})[0]["x"] == a ^ b
    mark = g.checkpoint()
    g.AND(g.OR(p, q), g.XOR(p, q))
    g.rollback(mark)
    assert g.checkpoint() == mark


def test_luby_sequence():
    assert [_luby(i) for i in range(15)] == [1, 1, 2, 1, 1, 2, 4, 1, 1, 2, 1, 1, 2, 4, 8]


def test_cdcl_agrees_with_brute_force_and_models_are_valid():
    rng = random.Random(1)

    def brute(cl, n):
        return any(all(any((bits[abs(l) - 1] if l > 0 else not bits[abs(l) - 1]) for l in c) for c in cl)
                   for bits in itertools.product([False, True], repeat=n))
    for _ in range(250):
        n = rng.randint(3, 9)
        cl = [[rng.choice([1, -1]) * rng.randint(1, n) for _ in range(rng.randint(1, 3))] for _ in range(rng.randint(n, 5 * n))]
        r, model = solve(cl, n)
        assert (r == "SAT") == brute(cl, n)
        if r == "SAT":
            assert all(any((model.get(abs(l), False) if l > 0 else not model.get(abs(l), False)) for l in c) for c in cl)


def test_cdcl_pigeonhole_unsat_and_conflict_limit():
    def php(p, h):
        v = lambda i, j: i * h + j + 1
        cl = [[v(i, j) for j in range(h)] for i in range(p)]
        for j in range(h):
            for a in range(p):
                for b in range(a + 1, p):
                    cl.append([-v(a, j), -v(b, j)])
        return cl, p * h
    cl, n = php(6, 5)
    assert solve(cl, n)[0] == "UNSAT"
    cl, n = php(9, 8)
    assert solve(cl, n, conflict_limit=50)[0] == "UNKNOWN"


# ---------------------------------------------------------------- CEC / BMC
def test_cec_proves_distinct_structures_and_refutes_with_verified_counterexample():
    def adder2(n):
        g = A.Aig()
        a = [g.new_input(f"a{i}") for i in range(n)]
        b = [g.new_input(f"b{i}") for i in range(n)]
        c = 0
        for i in range(n):
            g.add_output(f"s{i}", g.XOR(g.XOR(a[i], b[i]), c))
            c = g.OR(g.OR(g.AND(a[i], b[i]), g.AND(a[i], c)), g.AND(b[i], c))
        g.add_output("cout", c)
        return g
    r = combinational_equiv(B.ripple_adder(8), adder2(8))
    assert r.equivalent and r.method in ("sat-miter", "structural-hash")
    bad = adder2(6)
    n, l = bad.outputs[3]
    bad.outputs[3] = (n, l ^ 1)
    r = combinational_equiv(B.ripple_adder(6), bad)
    assert r.status == "NOT_EQUIVALENT" and r.counterexample


def test_bmc_and_matched_sequential_equivalence():
    cnt = B.BENCHMARKS["counter_4bit"].build()
    assert sequential_equiv_matched(cnt, optimize(cnt)).equivalent
    broken = elaborate((SEED_DIR / "counter_4bit.v").read_text().replace("count + 1'b1", "count + 2'b10"), "counter_4bit")
    r = bmc_equiv(cnt, broken, 6)
    assert r.status == "NOT_EQUIVALENT" and r.counterexample
    assert bmc_equiv(cnt, optimize(cnt), 6).equivalent


# ---------------------------------------------------------------- elaboration vs pysim
def _ports(mod):
    W = Widths(mod)
    ins, outs = [], []
    for p in mod.ports:
        if isinstance(p, PortDecl):
            (ins if p.direction == "input" else outs).extend((n, W.sig[n]) for n in p.names)
    return ins, outs


def _flat(name, w, v, d):
    for i in range(w):
        d[name if w == 1 else f"{name}[{i}]"] = (v >> i) & 1


def _pack(o, name, w):
    return sum(o[name if w == 1 else f"{name}[{i}]"] << i for i in range(w))


def test_elaborated_combinational_seeds_match_pysim():
    for name in ("alu_basic", "comparator_4bit"):
        src = (SEED_DIR / f"{name}.v").read_text()
        g = elaborate(src, name)
        mod = parse_source(src).modules[0]
        ins, outs = _ports(mod)
        sim = PySim(mod)
        rng = random.Random(0)
        for _ in range(300):
            vec = {n: rng.randrange(1 << w) for n, w in ins}
            inp = {}
            for n, w in ins:
                _flat(n, w, vec[n], inp)
            o, _, _ = g.simulate(inp)
            ref = sim.comb_eval(vec)
            assert all(_pack(o, n, w) == ref[n] for n, w in outs), (name, vec)


def test_elaborated_sequential_seeds_match_pysim_cycle_by_cycle():
    for name in ("counter_4bit", "fsm_seqdet", "mult_seq8"):
        src = (SEED_DIR / f"{name}.v").read_text()
        g = elaborate(src, name)
        mod = parse_source(src).modules[0]
        ins, outs = _ports(mod)
        sim, state, rng = PySim(mod), g.reset_state(), random.Random(2)
        for _ in range(600):
            vec = {}
            for n, w in ins:
                if n == "clk":
                    continue
                vec[n] = (0 if rng.random() < 0.05 else 1) if n == "rst_n" else (int(rng.random() < 0.3) if n == "start" else rng.randrange(1 << w))
            inp = {}
            for n, w in ins:
                if n != "clk":
                    _flat(n, w, vec[n], inp)
            _, state, _ = g.simulate(inp, state)       # clock edge
            o, _, _ = g.simulate(inp, state)           # outputs after the edge
            ref = sim.cycle(vec)
            assert all(_pack(o, n, w) == ref[n] for n, w in outs), name


def test_elaborator_fuzz_random_expressions_against_pysim():
    BIN = ["+", "-", "*", "&", "|", "^", "~^", "==", "!=", "<", "<=", ">", ">=", "<<", ">>", "&&", "||"]

    def gen(rng, d):
        if d == 0 or rng.random() < 0.2:
            r = rng.random()
            if r < 0.55:
                return rng.choice(["a", "b", "c"])
            if r < 0.7:
                return f"{rng.choice([1, 4, 8])}'d{rng.randrange(16)}"
            return rng.choice([f"a[{rng.randrange(8)}]", "b[5:2]", "s"])
        k = rng.random()
        if k < 0.55:
            return f"({gen(rng, d - 1)} {rng.choice(BIN)} {gen(rng, d - 1)})"
        if k < 0.7:
            return f"({rng.choice(['~', '!', '-', '&', '|', '^', '~&', '~|', '~^'])}{gen(rng, d - 1)})"
        if k < 0.82:
            return f"({gen(rng, d - 1)} ? {gen(rng, d - 1)} : {gen(rng, d - 1)})"
        if k < 0.92:
            return "{" + gen(rng, d - 1) + ", " + gen(rng, d - 1) + "}"
        return "{2{" + gen(rng, d - 1) + "}}"
    rng = random.Random(5)
    for _ in range(120):
        e = gen(rng, 3)
        src = f"module t(input [7:0] a, input [7:0] b, input [7:0] c, input s, output [15:0] y); assign y = {e}; endmodule"
        g, sim = elaborate(src, "t"), PySim(parse_source(src).modules[0])
        for _ in range(8):
            a, b, c, s = rng.randrange(256), rng.randrange(256), rng.randrange(256), rng.randrange(2)
            inp = {"s": s}
            for nm, v in (("a", a), ("b", b), ("c", c)):
                _flat(nm, 8, v, inp)
            got = _pack(g.simulate(inp)[0], "y", 16)
            assert got == sim.comb_eval({"a": a, "b": b, "c": c, "s": s})["y"], e


def test_hierarchy_parameters_and_unsupported_constructs():
    d = DESIGNS_DIR / "examples" / "hier_mac"
    src = "\n".join((d / f).read_text() for f in ("adder8.sv", "mult4.sv", "mac_top.sv"))
    g = elaborate(src, "mac_top")
    rng = random.Random(4)
    for _ in range(200):
        x, y, c = rng.randrange(16), rng.randrange(16), rng.randrange(256)
        inp = {}
        _flat("x", 4, x, inp), _flat("y", 4, y, inp), _flat("c", 8, c, inp)
        assert _pack(g.simulate(inp)[0], "result", 9) == (x * y + c) & 0x1FF
    param = ("module add #(parameter W = 4)(input [W-1:0] a, input [W-1:0] b, output [W:0] s); assign s = a + b; endmodule\n"
             "module top(input [7:0] a, input [7:0] b, output [8:0] s); add #(.W(8)) u(.a(a), .b(b), .s(s)); endmodule")
    gp = elaborate(param, "top")
    inp = {}
    _flat("a", 8, 200, inp), _flat("b", 8, 100, inp)
    assert _pack(gp.simulate(inp)[0], "s", 9) == 300
    for bad in ("module m(input [3:0] a, output [3:0] y); assign y = $signed(a); endmodule",
                "module m(input [3:0] a, input [3:0] b, output [3:0] y); assign y = a / b; endmodule"):
        try:
            elaborate(bad, "m")
        except Exception as e:
            assert "support" in str(e).lower() or "power of two" in str(e) or "Unsupported" in type(e).__name__
        else:
            raise AssertionError("expected an unsupported-construct error")


# ---------------------------------------------------------------- optimizer
def test_every_optimizer_pass_preserves_function_on_benchmarks():
    for name in ("c17", "adder8", "mult4", "cmp8", "parity16", "prio8", "popcount8", "redundant10", "shift8"):
        g = B.BENCHMARKS[name].build().cleanup()
        for fn in (rewrite, balance, fraig):
            o = fn(g)
            r = combinational_equiv(g, o)
            assert r.equivalent, (name, fn.__name__, r)
        full = optimize(g)
        assert full.num_ands() <= g.num_ands() and combinational_equiv(g, full).equivalent, name


def test_optimizer_finds_real_savings_on_redundant_and_rtl_logic():
    red = B.BENCHMARKS["redundant10"].build().cleanup()
    assert optimize(red).num_ands() < 0.5 * red.num_ands()
    alu = B.BENCHMARKS["alu_basic"].build().cleanup()
    o = optimize(alu)
    assert o.num_ands() < alu.num_ands() and combinational_equiv(alu, o).equivalent
    seq = B.BENCHMARKS["fsm_seqdet"].build().cleanup()
    so = optimize(seq)
    assert so.num_ands() <= seq.num_ands() and sequential_equiv_matched(seq, so).equivalent


def test_balance_reduces_depth_of_and_chains():
    g = A.Aig()
    xs = [g.new_input(f"x{i}") for i in range(16)]
    r = xs[0]
    for x in xs[1:]:
        r = g.AND(r, x)
    g.add_output("y", r)
    b = balance(g)
    assert g.depth() == 15 and b.depth() == 4 and combinational_equiv(g, b).equivalent


# ---------------------------------------------------------------- liberty / techmap / netlist
def test_liberty_parsing_tables_and_functions():
    assert len(LIB.cells) == 14 and LIB.cells["DFF"].is_ff and LIB.cells["DFF"].ff_next_state == "D"
    assert LIB.cells["NAND2"].truth_table() == 0b0111 and LIB.cells["AOI21"].truth_table() == 0b00000111
    assert LIB.cells["MUX2"].truth_table(["A", "B", "S"]) == 0b11001010
    arc = LIB.cells["NAND2"].pins["Y"].arcs[0]
    t = arc.tables["cell_rise"]
    assert t.lookup(0.02, 0.002) == t.values[0][0] and t.values[0][0] < t.lookup(0.08, 0.010) < t.values[2][2]
    lib2 = parse_liberty('library (x) { cell (G) { area : 1; pin (A) { direction : input; capacitance : 0.1; } '
                         'pin (Y) { direction : output; function : "A\'"; } } }')
    assert lib2.cells["G"].truth_table() == 0b01


def test_techmap_is_functionally_exact_for_both_objectives():
    for name in ("c17", "adder8", "cmp8", "prio8", "alu_basic"):
        g = optimize(B.BENCHMARKS[name].build())
        for obj in ("area", "delay"):
            nl = techmap(g, LIB, obj, name)
            assert combinational_equiv(g, nl.to_aig(LIB)).equivalent, (name, obj)
            ins = g.random_patterns(128, 9)
            assert g.simulate(ins, nbits=128)[0] == nl.simulate(LIB, ins, nbits=128)[0]
    a = techmap(optimize(B.BENCHMARKS["alu_basic"].build()), LIB, "area")
    d = techmap(optimize(B.BENCHMARKS["alu_basic"].build()), LIB, "delay")
    assert a.area(LIB) <= d.area(LIB)


def test_techmap_sequential_uses_flops_and_roundtrips():
    for name in ("counter_4bit", "fsm_seqdet"):
        g = optimize(B.BENCHMARKS[name].build())
        nl = techmap(g, LIB, "area", name)
        assert nl.stats(LIB)["flops"] == len(g.latches)
        assert sequential_equiv_matched(g, nl.to_aig(LIB)).equivalent
        v = nl.to_verilog(LIB)
        assert "DFF" in v and v.count("endmodule") == 1


# ---------------------------------------------------------------- STA / power
def _chain():
    nl = Netlist("chain")
    nl.inputs, nl.outputs = ["a"], ["y"]
    nl.add_cell("INV", {"A": "a", "Y": "n1"})
    nl.add_cell("INV", {"A": "n1", "Y": "n2"})
    nl.add_cell("INV", {"A": "n2", "Y": "n3"})
    nl.aliases["y"] = "n3"
    return nl


def test_sta_matches_hand_computed_inverter_chain():
    rep = analyze(_chain(), LIB, Constraints(period=1.0, default_load=0.005, input_transition=0.05))
    inv = LIB.cells["INV"].pins["Y"].arcs[0]
    best = 0.0
    for start in "rf":
        a, s, e = 0.0, 0.05, start
        for L in (0.0035, 0.0035, 0.005):
            oe = "f" if e == "r" else "r"
            a += inv.tables["cell_rise" if oe == "r" else "cell_fall"].lookup(s, L)
            s = inv.tables["rise_transition" if oe == "r" else "fall_transition"].lookup(s, L)
            e = oe
        best = max(best, a)
    assert abs(rep.endpoints[0]["arrival"] - best) < 1e-9 and abs(rep.wns - (1.0 - best)) < 1e-9
    assert [p.net for p in rep.critical_path] == ["a", "n1", "n2", "n3"]
    assert analyze(_chain(), LIB, Constraints(period=0.1)).wns < 0           # violated when the clock is too fast


def test_sta_flop_paths_setup_and_sdc_parsing():
    g = optimize(B.BENCHMARKS["counter_4bit"].build())
    nl = techmap(g, LIB, "area", "counter_4bit")
    sdc = ("create_clock -name clk -period 1.5 [get_ports clk]\nset_input_delay 0.2 -clock clk [all_inputs]\n"
           "set_output_delay 0.3 -clock clk [get_ports {count*}]\nset_load 0.02 [all_outputs]\n")
    cons = parse_sdc(sdc, nl)
    assert cons.period == 1.5 and cons.input_delay["en"] == 0.2 and cons.output_delay["count[0]"] == 0.3 and cons.load["count[1]"] == 0.02
    rep = analyze(nl, LIB, cons)
    kinds = {e["kind"] for e in rep.endpoints}
    assert kinds == {"flop", "output"} and rep.endpoints == sorted(rep.endpoints, key=lambda e: e["slack"])
    loose = analyze(nl, LIB, Constraints(period=50.0))
    assert loose.wns > rep.wns


def test_power_estimate_scales_with_frequency_and_has_leakage():
    nl = techmap(optimize(B.BENCHMARKS["adder8"].build()), LIB, "area", "adder8")
    slow = estimate_power(nl, LIB, Constraints(period=10.0))
    fast = estimate_power(nl, LIB, Constraints(period=2.0))
    assert fast["dynamic_uW"] > 4 * slow["dynamic_uW"] and abs(fast["leakage_uW"] - slow["leakage_uW"]) < 1e-12 and slow["leakage_uW"] > 0


# ---------------------------------------------------------------- formats / benchmarks / flow / regression / CLI
def test_c17_is_exact_and_formats_round_trip():
    g = B.BENCHMARKS["c17"].build()
    nand = lambda a, b: 1 - (a & b)
    for v in itertools.product([0, 1], repeat=5):
        i1, i2, i3, i6, i7 = v
        g11 = nand(i3, i6)
        g16 = nand(i2, g11)
        exp = (nand(nand(i1, i3), g16), nand(g16, nand(g11, i7)))
        o = g.simulate(dict(zip(["1", "2", "3", "6", "7"], v)))[0]
        assert (o["22"], o["23"]) == exp
    for name in ("c17", "adder8", "alu_basic"):
        a = B.BENCHMARKS[name].build()
        assert combinational_equiv(a, read_aag(write_aag(a))).equivalent and combinational_equiv(a, read_bench(write_bench(a))).equivalent
    for name in ("counter_4bit", "fsm_seqdet"):
        a = B.BENCHMARKS[name].build()
        assert sequential_equiv_matched(a, read_aag(write_aag(a))).equivalent and sequential_equiv_matched(a, read_bench(write_bench(a))).equivalent


def test_benchmark_generators_compute_the_right_functions():
    def val(g, vecs):
        inp = {}
        for nm, (v, w) in vecs.items():
            for i in range(w):
                inp[f"{nm}{i}"] = (v >> i) & 1
        return g.simulate(inp)[0]
    for a in range(16):
        for b in range(16):
            o = val(B.array_multiplier(4), {"a": (a, 4), "b": (b, 4)})
            assert sum(o[f"p{i}"] << i for i in range(8)) == a * b
            o = val(B.comparator(4), {"a": (a, 4), "b": (b, 4)})
            assert (o["eq"], o["lt"], o["gt"]) == (int(a == b), int(a < b), int(a > b))
    for x in range(256):
        assert sum(val(B.popcount(8), {"x": (x, 8)})[f"c{i}"] << i for i in range(4)) == bin(x).count("1")
        o = val(B.priority_encoder(8), {"r": (x, 8)})
        assert o["valid"] == int(x > 0) and (x == 0 or sum(o[f"idx{j}"] << j for j in range(3)) == x.bit_length() - 1)
    for x, k in itertools.product(range(0, 256, 17), range(8)):
        assert sum(val(B.barrel_shifter(8), {"x": (x, 8), "k": (k, 3)})[f"y{i}"] << i for i in range(8)) == (x << k) & 255


def test_flow_reports_verified_results_and_never_calls_sim_a_proof():
    r = run_flow(B.BENCHMARKS["redundant10"].build(), LIB, "redundant10")
    assert r["verified"] == "EQUIVALENT" and r["ands_after"] < r["ands_before"] and r["cells"] > 0 and r["area"] > 0
    big = B.array_multiplier(5)
    opt = balance(big)
    res = verify(big, rewrite(big), conflict_limit=10)
    assert res.status in ("EQUIVALENT", "SIM_ONLY")
    broken = B.ripple_adder(6)
    n, l = broken.outputs[2]
    broken.outputs[2] = (n, l ^ 1)
    s = sim_check(B.ripple_adder(6), broken)
    assert s.status == "NOT_EQUIVALENT" and sim_check(B.ripple_adder(6), B.ripple_adder(6)).status == "SIM_ONLY"


def test_regression_database_flags_real_regressions(tmp_path):
    con = connect(tmp_path / "r.db")
    rows = [run_flow(B.BENCHMARKS[n].build(), LIB, n) for n in ("c17", "adder8")]
    assert find_regressions(con, rows, "area", 2) == []          # nothing stored yet
    record(con, rows, "area", 2)
    assert find_regressions(con, rows, "area", 2) == []          # identical rerun
    worse = [dict(r) for r in rows]
    worse[1]["ands_after"] = int(worse[1]["ands_after"] * 1.5)
    worse[0]["verified"] = "NOT_EQUIVALENT"
    msgs = find_regressions(con, worse, "area", 2)
    assert any("adder8" in m and "AND nodes" in m for m in msgs) and any("NOT EQUIVALENT" in m for m in msgs)


def test_cli_end_to_end(tmp_path, capsys=None):
    out = tmp_path / "alu.v"
    assert cli_main(["flow", str(SEED_DIR / "comparator_4bit.v"), "--top", "comparator_4bit", "--out", str(out)]) == 0
    assert "module comparator_4bit" in out.read_text()
    assert cli_main(["cec", str(SEED_DIR / "alu_basic.v"), str(SEED_DIR / "alu_basic.v"), "--top", "alu_basic"]) == 0
    broken = tmp_path / "alu_basic.v"
    broken.write_text((SEED_DIR / "alu_basic.v").read_text().replace("a + b", "a - b", 1))
    assert cli_main(["cec", str(SEED_DIR / "alu_basic.v"), str(broken), "--top", "alu_basic"]) == 1
    assert cli_main(["bench", "list"]) == 0
