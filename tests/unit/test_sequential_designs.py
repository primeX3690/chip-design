"""Gap 'counter / FSM / multi-cycle multiplier': seeds are checked against independent golden models by REAL
(pure-Python) simulation, and the generated Verilator C++ testbenches contain the right ports/rows."""
from evohdl.hdl.parser import parse_source
from evohdl.hdl.pysim import PySim
from evohdl.paths import SEED_DIR
from evohdl.sandbox.testbench_generator import (
    MODULE_RENDERERS, MULT_SEQ8_LATENCY, MultSeq8Golden, SeqDetGolden, golden_mult_seq8_trace, golden_seqdet_trace,
    render_testbench,
)
from evohdl.symbolic_core.design_rule_checker import analyze_design_support, run_all_checks


def _sim(name):
    return PySim(parse_source((SEED_DIR / f"{name}.v").read_text()).modules[0])


def test_new_sequential_modules_are_registered():
    for m in ("counter_4bit", "fsm_seqdet", "mult_seq8"):
        assert m in MODULE_RENDERERS


def test_fsm_seed_matches_spec_level_golden_over_thousands_of_cycles():
    sim = _sim("fsm_seqdet")
    matches = 0
    for r, d, exp in golden_seqdet_trace(3000, seed=11):
        assert sim.cycle({"rst_n": r, "din": d})["match"] == exp
        matches += exp
    assert matches > 50  # the pattern really occurs, so the test is not vacuous


def test_fsm_golden_semantics_by_hand():
    g = SeqDetGolden()
    out = [g.step(1, b) for b in [1, 0, 1, 1, 0, 1, 1]]
    assert out == [0, 0, 0, 1, 0, 0, 1]          # overlapping detections
    assert g.step(0, 1) == 0 and g.step(1, 1) == 0   # reset clears history


def test_multiplier_seed_matches_transaction_golden_with_exact_latency():
    sim = _sim("mult_seq8")
    done_cycles = 0
    for (r, s, a, b), exp, chk in golden_mult_seq8_trace(4000, seed=5):
        got = sim.cycle({"rst_n": r, "start": s, "a": a, "b": b})
        for i, name in enumerate(("busy", "done", "product")):
            if (chk >> i) & 1:
                assert got[name] == exp[i], (name, got[name], exp[i])
        done_cycles += exp[1]
    assert done_cycles > 100


def test_multiplier_computes_correct_products_directly():
    sim = _sim("mult_seq8")
    sim.cycle({"rst_n": 0, "start": 0, "a": 0, "b": 0})
    for a, b in [(0, 0), (255, 255), (13, 11), (200, 3), (1, 128)]:
        sim.cycle({"rst_n": 1, "start": 1, "a": a, "b": b})
        for _ in range(MULT_SEQ8_LATENCY - 1):
            out = sim.cycle({"rst_n": 1, "start": 0, "a": 0, "b": 0})
            assert out["busy"] == 1 and out["done"] == 0
        out = sim.cycle({"rst_n": 1, "start": 0, "a": 0, "b": 0})
        assert out["done"] == 1 and out["busy"] == 0 and out["product"] == a * b


def test_multiplier_golden_ignores_start_while_busy():
    g = MultSeq8Golden()
    g.step(1, 1, 3, 4)
    for _ in range(3):
        g.step(1, 1, 99, 99)         # ignored
    for _ in range(MULT_SEQ8_LATENCY - 4):
        g.step(1, 0, 0, 0)
    busy, done, prod, chk = g.step(1, 0, 0, 0)
    assert (busy, done, prod) == (0, 1, 12)


def test_generated_testbenches_have_expected_structure():
    fsm = render_testbench("fsm_seqdet")
    assert "dut->rst_n = c.in[0];" in fsm and "dut->din = c.in[1];" in fsm and "dut->match" in fsm
    assert "EVOHDL_RESULT passed=%d total=%d" in fsm
    mult = render_testbench("mult_seq8")
    for port in ("rst_n", "start", "a", "b"):
        assert f"dut->{port} = c.in[" in mult
    for out in ("busy", "done", "product"):
        assert f"dut->{out}" in mult
    assert "uint32_t in[4];" in mult and "uint32_t exp[3];" in mult


def test_new_seeds_pass_static_checks_and_support_report():
    for m in ("fsm_seqdet", "mult_seq8"):
        src = (SEED_DIR / f"{m}.v").read_text()
        drc = run_all_checks(src)
        assert drc.passed, drc.violations
        msgs = analyze_design_support(src, m, "hybrid")
        assert not any(x.startswith("ERROR") for x in msgs)
        assert any("sequential" in x for x in msgs)
