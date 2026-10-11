module fsm_seqdet (clk, rst_n, din, match);
    wire _00_;
    wire _01_;
    wire _02_;
    wire _03_;
    wire _04_;
    wire _05_;
    wire _06_;
    wire _07_;
    input clk;
    wire clk;
    input din;
    wire din;
    output match;
    wire match;
    wire [2:0] next_state;
    input rst_n;
    wire rst_n;
    reg [2:0] state;
    assign _07_ = state[0] | state[1];
    assign _00_ = ~(state[2] & _07_);
    assign _01_ = ~(state[0] & state[1]);
    assign _02_ = din & _01_;
    assign next_state[0] = _00_ & _02_;
    assign _03_ = ~state[0] & ~state[2];
    assign _04_ = ~(state[1] & din);
    assign _05_ = _03_ ? _04_ : din;
    assign next_state[1] = _00_ & ~_05_;
    assign match = state[2] & ~_07_;
    assign _06_ = state[2] | ~din;
    assign next_state[2] = ~(_01_ | _06_);
    always @(posedge clk or negedge rst_n)
        if (!rst_n)
            state[2] <= 1'h0;
        else
            state[2] <= next_state[2];
    always @(posedge clk or negedge rst_n)
        if (!rst_n)
            state[1] <= 1'h0;
        else
            state[1] <= next_state[1];
    always @(posedge clk or negedge rst_n)
        if (!rst_n)
            state[0] <= 1'h0;
        else
            state[0] <= next_state[0];
endmodule
