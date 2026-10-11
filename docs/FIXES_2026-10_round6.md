# Round 6: the first real-tool result -- and what it exposed

User ran the formal pipeline on real Yosys against the shipped alu_basic "best" design:
`NOT_EQUIVALENT (yosys_sat_miter)`. (This is also the first confirmation that the combinational miter script is valid on a real Yosys.)

Root cause (reproduced offline with the in-house CEC): the "best" design differs from the seed only in
`zero_flag = (result == 8'b0) ? 1'b1 : 1'b0;` -> `? 1'b0 : 1'b0;`. The ALU testbench compared only `result` and `carry_out`; `zero_flag`
was never observed, so deleting its logic scored as a free area win (reward hacking / verification hole).

| Fix | Detail |
|---|---|
| Testbench | `alu_basic` C++ testbench now carries `expected_zero` and checks `dut->zero_flag` (compiled with g++ -Wall against C++ stand-ins: correct ALU 488/488; zero_flag-stuck ALU fails 66 vectors) |
| Regression tests | every registered testbench must read every declared output port; the exact bad mutant fails the new golden expectations (pysim) |
| Preflight guard | `analyze_design_support` flags outputs the testbench never checks (ERROR in simulation mode, WARN with formal modes) |
| Diagnostics | `python -m evohdl.doctor`: where evohdl runs from (editable-install path vs current dir), tools found, and what the last GA run really did (all-zero fitness, suspicious generation-0 score, old-format reports) |

Lesson for the product story: this is exactly the failure mode the wedge ("verified optimization") is meant to prevent. Run the GA with
`verification_mode: hybrid` (formal equivalence gates every candidate) so a mutant that changes behaviour can never become "best".
