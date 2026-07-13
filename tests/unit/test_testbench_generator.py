"""
Unit tests for 3_sandbox_time/testbench_generator.py's golden_alu() --
this is the ground truth every mutant is checked against, so it needs its
own independent verification.
Run: pytest tests/unit/test_testbench_generator.py -v
"""
from testbench_generator import golden_alu, generate_vectors, render_testbench


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
