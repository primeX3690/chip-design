// 16-bit logical left barrel shifter
module shift16 (
    input  wire [15:0] x,
    input  wire [3:0]  k,
    output wire [15:0] y
);
    assign y = x << k;
endmodule
