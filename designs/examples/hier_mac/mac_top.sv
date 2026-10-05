// Top: result = x*y + c, built from two sub-modules. List adder8.sv, mult4.sv BEFORE this file.
module mac_top (
    input  logic [3:0] x,
    input  logic [3:0] y,
    input  logic [7:0] c,
    output logic [8:0] result
);
    logic [7:0] prod;
    mult4  u_mult (.x(x), .y(y), .p(prod));
    adder8 u_add  (.a(prod), .b(c), .sum(result));
endmodule
