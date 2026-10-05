// 32:1 multiplexer
module mux32 (
    input  wire [31:0] d,
    input  wire [4:0]  s,
    output wire        y
);
    assign y = d[s];
endmodule
