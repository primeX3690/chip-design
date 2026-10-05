module mult4 (
    input  logic [3:0] x,
    input  logic [3:0] y,
    output logic [7:0] p
);
    always_comb p = x * y;
endmodule
