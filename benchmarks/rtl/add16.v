// 16-bit adder with carry out (arithmetic family)
module add16 (
    input  wire [15:0] a,
    input  wire [15:0] b,
    output wire [16:0] s
);
    assign s = a + b;
endmodule
