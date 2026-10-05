"""
Unit tests for evohdl/symbolic_core/design_rule_checker.py
Run: pytest tests/unit/test_design_rule_checker.py -v
"""
from evohdl.symbolic_core.design_rule_checker import run_all_checks


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


def test_analyze_design_support_flags_unregistered_module_and_sequential():
    from evohdl.symbolic_core.design_rule_checker import analyze_design_support
    src = "module foo(input clk, output reg q);\nalways @(posedge clk) q <= ~q;\nendmodule\n"
    msgs = analyze_design_support(src, "foo")
    assert any(m.startswith("ERROR") and "foo" in m for m in msgs)
    assert any("sequential" in m for m in msgs)
    assert any(m.startswith("WARN") and "foo" in m for m in analyze_design_support(src, "foo", "formal"))
    assert any("no `N'bXXX:` case branches" in m for m in msgs)


def test_analyze_design_support_clean_for_registered_alu():
    from evohdl.symbolic_core.design_rule_checker import analyze_design_support
    msgs = analyze_design_support(SEED_ALU, "alu_basic")
    assert not any(m.startswith("ERROR") for m in msgs)


def test_drc_handles_systemverilog_and_hierarchical_outputs():
    from evohdl.symbolic_core.design_rule_checker import run_all_checks
    from evohdl.sandbox.design_bundle import load_design_bundle
    from evohdl.paths import DESIGNS_DIR
    d = DESIGNS_DIR / "examples" / "hier_mac"
    b = load_design_bundle([d / "adder8.sv", d / "mult4.sv", d / "mac_top.sv"], top="mac_top")
    assert run_all_checks(b.source).passed, run_all_checks(b.source).violations


def test_drc_still_flags_a_truly_unassigned_output_and_concat_targets_count():
    from evohdl.symbolic_core.design_rule_checker import check_unconnected_output
    assert check_unconnected_output("module m(output logic [3:0] y); endmodule")
    assert not check_unconnected_output("module m(output [8:0] s, output c); assign {c, s} = 1; endmodule")
