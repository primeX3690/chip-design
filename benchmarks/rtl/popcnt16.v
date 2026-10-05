// population count of a 16-bit word
module popcnt16 (
    input  wire [15:0] x,
    output wire [4:0]  c
);
    assign c = x[0] + x[1] + x[2] + x[3] + x[4] + x[5] + x[6] + x[7]
             + x[8] + x[9] + x[10] + x[11] + x[12] + x[13] + x[14] + x[15];
endmodule
