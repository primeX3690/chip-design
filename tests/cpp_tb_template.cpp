// cpp_tb_template.cpp
// -----------------------------------------------------------------------
// Reference / documentation copy of the testbench structure EvoHDL
// generates dynamically at runtime (see 3_sandbox_time/testbench_generator.py).
// This static file is NOT compiled by the pipeline -- the real testbench
// is generated fresh for every evaluation so its embedded test vectors can
// be varied (random seed) or extended without editing C++ by hand.
//
// Kept here as documentation and as a manual smoke-test harness:
//   verilator --cc --exe --build -Wno-fatal \
//       --Mdir /tmp/evohdl_manual_tb -o sim.out \
//       designs/seed/alu_basic.v tests/cpp_tb_template.cpp
//   /tmp/evohdl_manual_tb/sim.out

#include <verilated.h>
#include "Valu_basic.h"
#include <cstdio>
#include <cstdint>

struct Vector {
    uint8_t a;
    uint8_t b;
    uint8_t opcode;
    uint8_t expected_result;
    uint8_t expected_carry;
};

// A small hand-written smoke-test subset (the generator produces ~350+ vectors).
static Vector vectors[] = {
    {0x00, 0x00, 0b000, 0x00, 0}, // ADD 0+0
    {0xFF, 0x01, 0b000, 0x00, 1}, // ADD overflow -> carry
    {0x05, 0x03, 0b001, 0x02, 0}, // SUB no borrow
    {0x00, 0x01, 0b001, 0xFF, 1}, // SUB underflow -> borrow
    {0xF0, 0x0F, 0b010, 0x00, 0}, // AND
    {0xF0, 0x0F, 0b011, 0xFF, 0}, // OR
    {0xFF, 0x0F, 0b100, 0xF0, 0}, // XOR
    {0x0F, 0x00, 0b101, 0xF0, 0}, // NOT
    {0x01, 0x00, 0b110, 0x02, 0}, // SHL
    {0x02, 0x00, 0b111, 0x01, 0}, // SHR
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Valu_basic* dut = new Valu_basic;

    int total = sizeof(vectors) / sizeof(Vector);
    int passed = 0;

    for (int i = 0; i < total; i++) {
        dut->a = vectors[i].a;
        dut->b = vectors[i].b;
        dut->opcode = vectors[i].opcode;
        dut->eval();

        bool ok = (dut->result == vectors[i].expected_result) &&
                  (dut->carry_out == vectors[i].expected_carry);
        if (ok) {
            passed++;
        } else {
            fprintf(stderr, "MISMATCH vec=%d a=%d b=%d op=%d got=%d exp=%d\n",
                    i, vectors[i].a, vectors[i].b, vectors[i].opcode,
                    dut->result, vectors[i].expected_result);
        }
    }

    printf("EVOHDL_RESULT passed=%d total=%d\n", passed, total);
    delete dut;
    return (passed == total) ? 0 : 1;
}
