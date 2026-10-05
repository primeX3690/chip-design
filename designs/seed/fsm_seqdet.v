// fsm_seqdet.v -- Moore FSM: detects the serial bit pattern 1011 (overlapping), async active-low reset.
// Sequential seed #2 for EvoHDL (FSM family). `match` is high for the cycle AFTER the 4th bit arrives.
// Correctness is defined by the golden model in testbench_generator.py (last four consumed bits == 1011),
// NOT by this state encoding, so a re-encoded FSM that behaves the same is a legal optimization.

module fsm_seqdet (
    input  wire clk,
    input  wire rst_n,
    input  wire din,
    output wire match
);

    localparam [2:0] S0 = 3'd0;   // no progress
    localparam [2:0] S1 = 3'd1;   // seen "1"
    localparam [2:0] S2 = 3'd2;   // seen "10"
    localparam [2:0] S3 = 3'd3;   // seen "101"
    localparam [2:0] S4 = 3'd4;   // seen "1011"  (match)

    reg [2:0] state;
    reg [2:0] next_state;

    always @(*) begin
        next_state = S0;
        case (state)
            S0: next_state = din ? S1 : S0;
            S1: next_state = din ? S1 : S2;
            S2: next_state = din ? S3 : S0;
            S3: next_state = din ? S4 : S2;
            S4: next_state = din ? S1 : S2;
            default: next_state = S0;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= S0;
        else
            state <= next_state;
    end

    assign match = (state == S4);

endmodule
