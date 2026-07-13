"""
Unit tests for 1_symbolic_core/design_rule_checker.py
Run: pytest tests/unit/test_design_rule_checker.py -v
"""
from design_rule_checker import run_all_checks


SEED_ALU = """
module alu_basic (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire [2:0] opcode,
    output reg  [7:0] result,
    output reg        carry_out,
    output reg        zero_flag
);
    always @(*) begin
        carry_out = 1'b0;
        case (opcode)
            3'b000: {carry_out, result} = a + b;
            3'b001: {carry_out, result} = a - b;
            default: result = 8'b0;
        endcase
        zero_flag = (result == 8'b0) ? 1'b1 : 1'b0;
    end
endmodule
"""


def test_valid_design_passes():
    report = run_all_checks(SEED_ALU)
    assert report.passed
    assert report.violations == []


def test_unbalanced_begin_end_is_caught():
    broken = SEED_ALU.replace("endmodule", "begin\nendmodule")
    report = run_all_checks(broken)
    assert not report.passed
    assert any("begin/end" in v for v in report.violations)


def test_empty_case_branch_is_caught():
    broken = SEED_ALU.replace(
        "3'b001: {carry_out, result} = a - b;",
        "3'b001: ;",
    )
    report = run_all_checks(broken)
    assert not report.passed
    assert any("empty case branch" in v for v in report.violations)


def test_multiple_drivers_is_caught():
    broken = SEED_ALU.replace(
        "endmodule",
        "assign result = a;\nendmodule",
    )
    report = run_all_checks(broken)
    assert not report.passed
    assert any("multiple drivers" in v or "both assign and always" in v for v in report.violations)


def test_infinite_for_loop_is_caught():
    broken = SEED_ALU.replace(
        "always @(*) begin",
        "always @(*) begin\n        for (integer i = 0; i < 8;) begin end",
    )
    report = run_all_checks(broken)
    assert not report.passed
    assert any("infinite loop" in v for v in report.violations)
