# golden_outputs/

EvoHDL currently uses an in-code Python golden reference
(`golden_alu()` in `3_sandbox_time/testbench_generator.py`) rather than
static golden-output files, so the reference model can never drift out of
sync with the generated testbench.

This directory is reserved for teams that outgrow that approach -- e.g. if
you evolve a design too complex to model as a pure Python function (a
multi-cycle CPU, a UART, etc.), drop expected-output vector files here
(one line per test case: inputs,expected_outputs) and update
`testbench_generator.py`'s `generate_vectors()` to read from this
directory instead of calling `golden_alu()` directly.
