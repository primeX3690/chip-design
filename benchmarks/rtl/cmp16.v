// 16-bit magnitude comparator
module cmp16 (
    input  wire [15:0] a,
    input  wire [15:0] b,
    output wire        eq,
    output wire        lt,
    output wire        gt
);
    assign eq = (a == b);
    assign lt = (a <  b);
    assign gt = (a >  b);
endmodule
