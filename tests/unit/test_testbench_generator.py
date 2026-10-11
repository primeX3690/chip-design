"""
Unit tests for evohdl/sandbox/testbench_generator.py's golden_alu() --
this is the ground truth every mutant is checked against, so it needs its
own independent verification.
Run: pytest tests/unit/test_testbench_generator.py -v
"""
from evohdl.sandbox.testbench_generator import golden_alu, generate_vectors, render_testbench


def test_add_no_overflow():
    result, carry = golden_alu(1, 2, 0b000)
    assert result == 3
    assert carry == 0


def test_add_overflow_sets_carry():
    result, carry = golden_alu(255, 1, 0b000)
    assert result == 0
    assert carry == 1


def test_sub_no_borrow():
    result, carry = golden_alu(5, 3, 0b001)
    assert result == 2
    assert carry == 0


def test_sub_underflow_sets_carry_as_borrow():
    result, carry = golden_alu(0, 1, 0b001)
    assert result == 255
    assert carry == 1


def test_bitwise_and():
    result, _ = golden_alu(0b11110000, 0b00001111, 0b010)
    assert result == 0


def test_bitwise_or():
    result, _ = golden_alu(0b11110000, 0b00001111, 0b011)
    assert result == 0xFF


def test_bitwise_xor():
    result, _ = golden_alu(0xFF, 0x0F, 0b100)
    assert result == 0xF0


def test_not():
    result, _ = golden_alu(0x0F, 0x00, 0b101)
    assert result == 0xF0


def test_shift_left_drops_msb():
    result, _ = golden_alu(0b10000001, 0x00, 0b110)
    assert result == 0b00000010


def test_shift_right_drops_lsb():
    result, _ = golden_alu(0b00000011, 0x00, 0b111)
    assert result == 0b00000001


def test_generate_vectors_covers_all_opcodes():
    vectors = generate_vectors(num_random=10, seed=1)
    opcodes_seen = {v[2] for v in vectors}
    assert opcodes_seen == set(range(8))


def test_generate_vectors_is_reproducible_with_seed():
    v1 = generate_vectors(num_random=50, seed=99)
    v2 = generate_vectors(num_random=50, seed=99)
    assert v1 == v2


def test_render_testbench_embeds_module_name():
    cpp = render_testbench("alu_basic", num_random_vectors=5, seed=1)
    assert "Valu_basic.h" in cpp
    assert "EVOHDL_RESULT" in cpp


def test_every_registered_testbench_observes_every_declared_output():
    """Regression for the zero_flag hole: the GA 'optimized' alu_basic by breaking an output nobody checked
    (best 245 cells, formally NOT equivalent). Every output port of every registered seed must be read by its testbench."""
    from evohdl.paths import SEED_DIR
    from evohdl.sandbox.testbench_generator import MODULE_RENDERERS
    from evohdl.eda.aig_verilog import module_ports
    for name in MODULE_RENDERERS:
        src = (SEED_DIR / f"{name}.v").read_text()
        tb = render_testbench(name)
        missing = [n for d, n, w in module_ports(src, name) if d == "output" and f"dut->{n}" not in tb]
        assert not missing, f"{name}: outputs never checked by the testbench: {missing}"


def test_alu_testbench_checks_zero_flag_with_correct_expectations():
    tb = render_testbench("alu_basic")
    assert "dut->zero_flag == vectors[i].expected_zero" in tb
    assert "{0, 0, 0, 0, 0, 1}," in tb          # a=0,b=0,ADD -> result 0 -> zero_flag expected 1
    assert "{1, 0, 0, 1, 0, 0}," in tb          # 1+0 -> 1 -> zero_flag expected 0


def test_a_zero_flag_breaking_mutant_is_caught_by_the_new_golden_expectations():
    """The exact bad 'best' design that used to score 245 cells: zero_flag stuck at 0. Simulate it against the golden
    expectations the testbench now embeds -> it must fail."""
    import re
    from evohdl.hdl.parser import parse_source
    from evohdl.hdl.pysim import PySim
    from evohdl.paths import SEED_DIR
    src = (SEED_DIR / "alu_basic.v").read_text()
    bad = src.replace("(result == 8'b0) ? 1'b1 : 1'b0", "(result == 8'b0) ? 1'b0 : 1'b0")
    assert bad != src
    sim = PySim(parse_source(bad).modules[0])
    tb = render_testbench("alu_basic")
    rows = re.findall(r"\{(\d+), (\d+), (\d+), (\d+), (\d+), (\d+)\},", tb)
    failures = 0
    for a, b, op, r, c, z in rows:
        out = sim.comb_eval({"a": int(a), "b": int(b), "opcode": int(op)})
        if (out["result"], out["carry_out"], out["zero_flag"]) != (int(r), int(c), int(z)):
            failures += 1
    assert failures > 0
    good = PySim(parse_source(src).modules[0])
    assert all((lambda o: (o["result"], o["carry_out"], o["zero_flag"]) == (int(r), int(c), int(z)))(
        good.comb_eval({"a": int(a), "b": int(b), "opcode": int(op)})) for a, b, op, r, c, z in rows)
