// counter_4bit.v
// Add to: rtl_modules/counter_4bit.v  (next to your alu_basic.v)
//
// Second seed module for EvoHDL — run the same GA pipeline on this
// to prove the evolution approach generalizes beyond alu_basic.
// It's deliberately simple (small search space) so you get a clean
// first result fast; add a bigger module (FSM/memory controller)
// once this one shows convergence.

module counter_4bit (
    input  wire       clk,
    input  wire       rst_n,
    input  wire        en,
    output reg  [3:0] count
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 4'b0100;
        else if (en)
            count <= count + 1'b1;
    end

endmodule