# Round 5: turning the wedge into testable evidence

| Item | Built | Verified |
|---|---|---|
| Head-to-head harness | `evohdl/eda/compare.py`, CLI `evohdl.eda compare`, `scripts/run_head_to_head.sh` | script generation, old/new Yosys output formats, win/tie/loss logic, unverified-never-a-win rule, unsupported/sequential reporting, no-Yosys banner: 8 tests with mocked Yosys |
| Verified pre-pass emitter | `evohdl/eda/aig_verilog.py` (optimized AIG -> flat Verilog with the ORIGINAL ports) | on all 13 native-supported combinational benchmarks: ports identical, re-elaboration proven equivalent, original-vs-optimized proven equivalent |
| Benchmark suite for RTL flows | `benchmarks/rtl/*.v` (11 arithmetic/control/DSP blocks) + `benchmarks/suite.json` (18 entries incl. seeds, hierarchical, one deliberately unsupported) | each block checked against a Python reference function |
| FPGA proof script | `scripts/fpga_ice40_demo.sh` | **not run** (no tools/board here) |
| Business docs | `docs/WEDGE_PLAN.md`, `docs/CUSTOMER_DISCOVERY.md`, `benchmarks/EXTERNAL.md` | n/a (plans, with explicit go/no-go criteria and claims policy) |

Honest state: the native pre-pass changes AND counts on some blocks (cmp16 173->123, prio16 88->69, popcnt16 249->217) and
nothing on adders/multipliers/parity/mux/shifters. Whether that survives ABC remapping is exactly what the harness measures
and what has NOT been measured. Sequential designs and designs outside the native subset (e.g. `$signed`, generate) get no pre-pass.
