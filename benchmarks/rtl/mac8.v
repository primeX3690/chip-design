// multiply-accumulate: a*b + c
module mac8 (
    input  wire [7:0]  a,
    input  wire [7:0]  b,
    input  wire [15:0] c,
    output wire [16:0] y
);
    assign y = a * b + c;
endmodule
