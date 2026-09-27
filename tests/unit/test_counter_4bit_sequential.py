"""
tests/unit/test_counter_4bit_sequential.py

Regression test for the Stage-3 addition (2026-09): counter_4bit is the
first SEQUENTIAL (clocked) design wired into the automated GA pipeline via
3_sandbox_time/testbench_generator.py's MODULE_RENDERERS registry. Before
this, every module in the registry was purely combinational.

This test does NOT need Verilator/Yosys installed -- it only exercises the
pure-Python golden model and CPP-rendering code, cross-checked against the
exact scenarios in the hand-written tests/counter_4bit_tb.v so both stay
in agreement.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "3_sandbox_time"))

from testbench_generator import (  # noqa: E402
    MODULE_RENDERERS,
    golden_counter_4bit_step,
    render_testbench,
)


def test_counter_4bit_is_registered():
    assert "counter_4bit" in MODULE_RENDERERS, (
        "counter_4bit has a seed design and a config file but was never "
        "wired into MODULE_RENDERERS -- the GA pipeline can't evaluate it."
    )


def test_golden_model_matches_handwritten_verilog_testbench_scenarios():
    """Mirrors tests/counter_4bit_tb.v's three scenarios exactly so the
    Python golden model used for GA fitness never silently drifts out of
    sync with the human-written correctness spec."""
    count = 0

    # Scenario 1: reset, then 20 cycles of en=1 -> 20 % 16 == 4
    count = golden_counter_4bit_step(rst_n=0, en=0, prev_count=count)
    for _ in range(20):
        count = golden_counter_4bit_step(rst_n=1, en=1, prev_count=count)
    assert count == 4

    # Scenario 2: en=0 for 5 cycles freezes the count
    for _ in range(5):
        count = golden_counter_4bit_step(rst_n=1, en=0, prev_count=count)
    assert count == 4

    # Scenario 3: async reset (rst_n=0) overrides en=1 immediately
    count = golden_counter_4bit_step(rst_n=0, en=1, prev_count=count)
    assert count == 0


def test_golden_model_wraps_at_4_bits():
    count = 15
    count = golden_counter_4bit_step(rst_n=1, en=1, prev_count=count)
    assert count == 0, "4-bit counter must wrap 15 -> 0, not overflow"


def test_render_testbench_produces_compilable_looking_cpp():
    cpp = render_testbench("counter_4bit", num_random_vectors=50, seed=1)
    assert "Vcounter_4bit.h" in cpp
    assert "EVOHDL_RESULT passed=" in cpp
    assert "struct Cycle" in cpp
    assert cpp.count("dut->clk = 0;") == 1 and cpp.count("dut->clk = 1;") == 1, (
        "testbench must toggle clk low-then-high exactly once per cycle "
        "inside the loop body"
    )
