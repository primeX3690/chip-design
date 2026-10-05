// sum of absolute differences of two 4-element vectors of 6-bit pixels (typical DSP/vision kernel)
module sad4 (
    input  wire [5:0] a0, a1, a2, a3,
    input  wire [5:0] b0, b1, b2, b3,
    output wire [7:0] sad
);
    wire [5:0] d0 = (a0 > b0) ? (a0 - b0) : (b0 - a0);
    wire [5:0] d1 = (a1 > b1) ? (a1 - b1) : (b1 - a1);
    wire [5:0] d2 = (a2 > b2) ? (a2 - b2) : (b2 - a2);
    wire [5:0] d3 = (a3 > b3) ? (a3 - b3) : (b3 - a3);
    assign sad = d0 + d1 + d2 + d3;
endmodule
