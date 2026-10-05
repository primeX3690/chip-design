// Example sub-module for the hierarchical / SystemVerilog flow (gap H demo).
module adder8 (
    input  logic [7:0] a,
    input  logic [7:0] b,
    output logic [8:0] sum
);
    always_comb sum = a + b;
endmodule
