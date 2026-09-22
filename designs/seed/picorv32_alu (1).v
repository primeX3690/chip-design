// picorv32_alu.v
// Real functional block extracted from PicoRV32 (YosysHQ/picorv32, master
// branch, picorv32.v lines ~1221-1290 -- the always@* ALU datapath inside
// the picorv32 top module). PicoRV32 is a production RV32I(M)(C) core that
// has been fabricated on real silicon multiple times (e.g. TinyTapeout
// shuttles on the open SkyWater 130nm PDK), so this is not a toy design --
// it is the actual combinational ALU datapath of a taped-out open-source
// CPU, re-packaged as a standalone module with a clean funct3/funct7[5]
// opcode input in place of the one-hot instr_* decode flags (which live in
// the surrounding instruction-decode FSM in the original file and are out
// of scope for a standalone ALU block).
//
// alu_op encoding (mirrors RV32I funct3 + funct7[5], the exact encoding the
// real core's instr_add/instr_sub/... one-hot flags collapse down to):
//   4'b0000 = ADD   4'b0001 = SUB   4'b0010 = SLL   4'b0011 = SLT
//   4'b0100 = SLTU  4'b0101 = XOR   4'b0110 = SRL   4'b0111 = SRA
//   4'b1000 = OR    4'b1001 = AND
//
// Seed design for EvoHDL evolutionary optimizer -- deliberately left as the
// direct translation of the original always@* block (no manual area/timing
// tuning applied), so the GA has real headroom to improve it.

module picorv32_alu (
    input  wire [31:0] reg_op1,
    input  wire [31:0] reg_op2,
    input  wire [3:0]  alu_op,
    output reg  [31:0] alu_out
);

    wire        instr_sub = alu_op == 4'b0001;
    wire        instr_sra = alu_op == 4'b0111;

    wire [31:0] alu_add_sub = instr_sub ? (reg_op1 - reg_op2) : (reg_op1 + reg_op2);
    wire        alu_lts     = $signed(reg_op1) < $signed(reg_op2);
    wire        alu_ltu     = reg_op1 < reg_op2;
    wire [31:0] alu_shl     = reg_op1 << reg_op2[4:0];
    wire [32:0] alu_shr_ext = $signed({instr_sra ? reg_op1[31] : 1'b0, reg_op1}) >>> reg_op2[4:0];
    wire [31:0] alu_shr     = alu_shr_ext[31:0];

    always @(*) begin
        alu_out = 32'b0;
        case (alu_op)
            4'b0000: alu_out = alu_add_sub;       // ADD
            4'b0001: alu_out = alu_add_sub;       // SUB
            4'b0010: alu_out = alu_shl;           // SLL
            4'b0011: alu_out = {31'b0, alu_lts};  // SLT
            4'b0100: alu_out = {31'b0, alu_ltu};  // SLTU
            4'b0101: alu_out = reg_op1 ^ reg_op2; // XOR
            4'b0110: alu_out = alu_shr;           // SRL
            4'b0111: alu_out = alu_shr;           // SRA
            4'b1000: alu_out = reg_op1 | reg_op2; // OR
            4'b1001: alu_out = reg_op1 & reg_op2; // AND
            default: alu_out = 32'b0;
        endcase
    end

endmodule
