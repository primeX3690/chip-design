// 32-bit adder with carry out
module add32 (
    input  wire [31:0] a,
    input  wire [31:0] b,
    output wire [32:0] s
);
    assign s = a + b;
endmodule
