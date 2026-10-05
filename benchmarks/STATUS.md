# What is and is not measured (honest status)

| Claim | Status |
|---|---|
| Mutants are checked for functional correctness (Verilator, 300-950 vectors) | Implemented; needs Verilator to run |
| Generic Yosys cell count / logic depth as the GA fitness proxy | Implemented; needs Yosys to run |
| GA finds smaller/faster RTL than the human-written seed | **Not demonstrated.** Best recorded runs: picorv32_alu 0.0%, alu_basic ~3% on cell count |
| Real sky130 die area (OpenLane) | **Never run.** Needs Docker or the `hardware_verification` GitHub workflow |
| Real sky130 timing (OpenSTA) | **Never run** |
| FPGA place-and-route (nextpnr-ice40) | Run once: 15.45 ns routed critical path, 648/7680 LUTs on picorv32_alu |
| Per-generation formal equivalence (hybrid/formal mode), eval cache, island model | **Implemented 2026-10, unit-tested with mocked tools; no speedup or improvement measured yet** |
| Yosys pass-pipeline / `abc -g` mutations | **Implemented 2026-10; recipes not yet validated against a real Yosys** (an invalid pass for your Yosys version is a safe no-op) |
| AST parser + 10 syntax-tree operators | **Implemented and verified offline**: round-trip on all seeds; each operator differentially simulated (pure Python) original-vs-mutant on random stimulus; chained mutations stay equivalent. Real-tool acceptance rates unknown |
| fsm_seqdet / mult_seq8 seeds + testbenches | Seeds match independent golden models in pure-Python simulation (3000-4000 cycles); generated C++ testbenches compile (g++ -Wall) and pass against C++ stand-ins. **Not run through Verilator or the GA** |
| Automated formal pipeline (SAT / equiv_make / eqy / BMC) | **Implemented; orchestration unit-tested with mocked tools.** The Yosys/eqy scripts themselves are unverified until `python -m evohdl.sandbox.formal_pipeline --selftest` is run |
| Native EDA kernel (elaborate / optimize / CEC / map / STA / power) | **Implemented and tested offline (172 unit tests, all pure Python).** Elaborator fuzzed against pysim; every optimizer pass and every mapped netlist proven equivalent by the in-house CEC on the benchmark set (mult6: simulation only). Library is fictional; no physical design |
| Benchmark baseline (`benchmarks/eda_regression.db`) | 17 circuits recorded with this flow version; `python -m evohdl.eda regress` exits 1 on regressions |
| Head-to-head vs Yosys+ABC (`evohdl.eda compare`) + verified pre-pass | **Harness implemented and unit-tested with a mocked Yosys (180 tests); pre-pass output proven equivalent on all 13 native-supported combinational benchmarks by in-house CEC and Verilog round trip. NO real Yosys result exists yet, so no claim of improvement is made.** The shipped baseline numbers use a fictional library |
| FPGA demo / silicon | Script (`scripts/fpga_ice40_demo.sh`) written, **never run**; no board or chip measurement exists |
| Hierarchical / SystemVerilog seeds | **Implemented 2026-10 for the Yosys built-in SV subset; only exercised with mocks** (`--selftest` exercises the real scripts) |
| Formal equivalence seed vs best | Implemented (Yosys miter + SAT); only runs in the post-run hardware pipeline, not per generation; bounded for sequential designs |

To produce real numbers: see README "Real Hardware Verification Flow". Re-run the GA, then
`python run_self_learner.py --config config/config_picorv32_alu.yaml --full-verify`.
