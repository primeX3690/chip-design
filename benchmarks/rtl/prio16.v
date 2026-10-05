// 16-request priority encoder: index of the highest set bit
module prio16 (
    input  wire [15:0] r,
    output wire        valid,
    output wire [3:0]  idx
);
    assign valid = |r;
    assign idx = r[15] ? 4'd15 : r[14] ? 4'd14 : r[13] ? 4'd13 : r[12] ? 4'd12 :
                 r[11] ? 4'd11 : r[10] ? 4'd10 : r[9]  ? 4'd9  : r[8]  ? 4'd8  :
                 r[7]  ? 4'd7  : r[6]  ? 4'd6  : r[5]  ? 4'd5  : r[4]  ? 4'd4  :
                 r[3]  ? 4'd3  : r[2]  ? 4'd2  : r[1]  ? 4'd1  : 4'd0;
endmodule
