// 32-bit parity (XOR reduction)
module parity32 (
    input  wire [31:0] x,
    output wire        p
);
    assign p = ^x;
endmodule
