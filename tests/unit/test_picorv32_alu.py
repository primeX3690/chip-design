"""
Unit tests for 3_sandbox_time/testbench_generator.py's golden_picorv32_alu()
-- the ground truth picorv32_alu mutants are checked against. Mirrors
test_testbench_generator.py's structure for the original alu_basic model.
Run: pytest tests/unit/test_picorv32_alu.py -v
"""
from testbench_generator import golden_picorv32_alu, render_testbench, MODULE_RENDERERS


def test_add():
    assert golden_picorv32_alu(1, 2, 0b0000) == 3


def test_add_wraps_mod_2_32():
    assert golden_picorv32_alu(0xFFFFFFFF, 1, 0b0000) == 0


def test_sub():
    assert golden_picorv32_alu(5, 3, 0b0001) == 2


def test_sub_wraps_mod_2_32():
    assert golden_picorv32_alu(0, 1, 0b0001) == 0xFFFFFFFF


def test_sll():
    assert golden_picorv32_alu(1, 4, 0b0010) == 0x10


def test_slt_signed():
    # -1 (0xFFFFFFFF) < 1 is true under signed comparison
    assert golden_picorv32_alu(0xFFFFFFFF, 1, 0b0011) == 1


def test_sltu_unsigned():
    # 0xFFFFFFFF is NOT < 1 under unsigned comparison
    assert golden_picorv32_alu(0xFFFFFFFF, 1, 0b0100) == 0


def test_xor():
    assert golden_picorv32_alu(0xFF, 0x0F, 0b0101) == 0xF0


def test_srl_zero_fills():
    assert golden_picorv32_alu(0x80000000, 4, 0b0110) == 0x08000000


def test_sra_sign_extends():
    assert golden_picorv32_alu(0x80000000, 4, 0b0111) == 0xF8000000


def test_or():
    assert golden_picorv32_alu(0xF0, 0x0F, 0b1000) == 0xFF


def test_and():
    assert golden_picorv32_alu(0xFF, 0x0F, 0b1001) == 0x0F


def test_module_registered_in_dispatch():
    assert "picorv32_alu" in MODULE_RENDERERS


def test_render_testbench_embeds_module_name():
    cpp = render_testbench("picorv32_alu", num_random_vectors=5, seed=1)
    assert "Vpicorv32_alu.h" in cpp
    assert "EVOHDL_RESULT" in cpp
    assert "reg_op1" in cpp and "alu_out" in cpp
