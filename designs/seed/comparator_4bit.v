// comparator_4bit.v
// A second seed design for EvoHDL, used to show the evolutionary engine
// generalizes beyond the ALU. Deliberately verbose/non-optimal 4-bit
// magnitude comparator -- lots of room for the GA to shrink it.
//
// NOTE: this design has a DIFFERENT port contract than alu_basic.v, so it
// needs its own testbench. See notes at the bottom of this file for the
// two-line change required in 3_sandbox_time/testbench_generator.py to
// point it at a comparator-specific golden model instead of golden_alu().

module comparator_4bit (
    input  wire [3:0] x,
    input  wire [3:0] y,
    output reg         eq,
    output reg         gt,
    output reg         lt
);

    always @(*) begin
        if (x == y) begin
            eq = 1'b1;
            gt = 1'b0;
            lt = 1'b0;
        end else if (x > y) begin
            eq = 1'b0;
            gt = 1'b1;
            lt = 1'b0;
        end else begin
            eq = 1'b0;
            gt = 1'b0;
            lt = 1'b1;
        end
    end

endmodule

// --- To evolve this design instead of alu_basic ---------------------------
// 1. Add a `golden_comparator(x, y) -> (eq, gt, lt)` function to
//    3_sandbox_time/testbench_generator.py (mirrors golden_alu()).
// 2. Add a comparator-specific CPP_TEMPLATE variant (3-output struct
//    instead of result/carry_out) and a render_comparator_testbench()
//    function.
// 3. In config/system_config.yaml, set:
//      module_name: comparator_4bit
//      seed_design: designs/seed/comparator_4bit.v
// This is intentionally left as an extension point rather than baked in --
// keeping one clean golden model per design keeps the correctness
// guarantee airtight (see README.md "Current Limitations").
