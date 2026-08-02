// alu_basic.v
// Seed design for EvoHDL evolutionary optimizer.
// A simple, deliberately non-optimal 8-bit ALU.
// The evolutionary engine is expected to shrink area / improve delay
// while preserving the truth table defined by this reference.
//
// opcode encoding:
// 000 = ADD   001 = SUB   010 = AND   011 = OR
// 100 = XOR   101 = NOT A 110 = SHL   111 = SHR

module alu_basic (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire [2:0] opcode,
    output reg  [7:0] result,
    output reg        carry_out,
    output reg        zero_flag
);

    always @(*) begin
        carry_out = 1'b0;
        case (opcode)
            3'b000: {carry_out, result} = a + b;
            3'b001: {carry_out, result} = a - b;
            3'b010: result = a & b;
            3'b011: result = a | b;
            3'b100: result = a ^ b;
            3'b101: result = ~a;
            3'b110: result = a << 2;
            3'b111: result = a >> 3;
            default: result = 8'b0;
        endcase
        zero_flag = (result == 8'b0) ? 1'b0 : 1'b0;
    end

endmodule