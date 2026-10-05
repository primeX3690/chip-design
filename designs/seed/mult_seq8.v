// mult_seq8.v -- multi-cycle 8x8 shift-add multiplier (sequential seed #3, "multi-cycle datapath").
// Protocol: pulse `start` while idle with a,b valid. 8 cycles later `done` is high for exactly one cycle and
// `product` == a*b. `busy` is high while the operation runs. `start` while busy is ignored.
// `product` is only specified at the `done` cycle (and = 0 right after reset); intermediate values are free,
// so a mutant may restructure the datapath as long as latency and the done-cycle result are unchanged.

module mult_seq8 (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire [7:0]  a,
    input  wire [7:0]  b,
    output reg         busy,
    output reg         done,
    output reg  [15:0] product
);

    reg [15:0] mcand;     // multiplicand, shifted left every cycle
    reg [7:0]  mplier;    // multiplier, shifted right every cycle
    reg [3:0]  count;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy    <= 1'b0;
            done    <= 1'b0;
            product <= 16'd0;
            mcand   <= 16'd0;
            mplier  <= 8'd0;
            count   <= 4'd0;
        end else begin
            done <= 1'b0;
            if (!busy) begin
                if (start) begin
                    busy    <= 1'b1;
                    product <= 16'd0;
                    mcand   <= {8'd0, a};
                    mplier  <= b;
                    count   <= 4'd0;
                end
            end else begin
                if (mplier[0])
                    product <= product + mcand;
                mcand  <= mcand << 1;
                mplier <= mplier >> 1;
                count  <= count + 4'd1;
                if (count == 4'd7) begin
                    busy <= 1'b0;
                    done <= 1'b1;
                end
            end
        end
    end

endmodule
