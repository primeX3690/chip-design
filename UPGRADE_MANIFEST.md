# EvoHDL Upgrade Manifest (2026-09)

Implements the 5 requested points (real block, real benchmarking, real
OpenLane/sky130, real OpenSTA, real nextpnr) plus 2 bugs found and fixed
along the way. Verified with real Yosys 0.33 + Verilator 5.020 +
nextpnr-ice40 (installed and run for real while building this).

## New files

- `designs/seed/picorv32_alu.v` -- real 32-bit RV32I ALU extracted from
  PicoRV32 (silicon-taped-out core), replaces alu_basic as the "real
  block" seed design. 940/940 test vectors pass against a Python golden
  model, verified with Verilator.
- `config/config_picorv32_alu.yaml` -- run config for the new module.
- `4_self_improve_loop/openlane_runner.py` -- real OpenLane + SkyWater
  130nm PDK flow wrapper (needs Docker on your machine to actually run;
  not testable in the sandbox this was built in).
- `4_self_improve_loop/opensta_runner.py` + `flow/opensta/run_sta.tcl` --
  real OpenSTA static timing analysis wrapper (needs a from-source OpenSTA
  build; not testable in the sandbox this was built in).
- `4_self_improve_loop/nextpnr_runner.py` -- real iCE40 place-and-route
  wrapper. TESTED FOR REAL: 15.45ns routed critical path, 648/7680 LUTs on
  picorv32_alu.
- `4_self_improve_loop/hardware_verification_pipeline.py` -- chains all
  four stages above into one `benchmarks/hardware_verification_report.md`.
  TESTED FOR REAL (stages 1 + 4; stages 2 + 3 correctly report
  "Not available" without Docker/OpenSTA installed).
- `flow/openlane/config.json` -- OpenLane design config template.
- `tests/unit/test_picorv32_alu.py` -- 14 new unit tests, all passing.
- `.gitignore` -- was missing; __pycache__/, per-run designs/gen_*/, etc.

## Modified files

- `2_evolutionary_engine/verilog_mutator.py` -- generalized the
  `3'b[01]{3}`-only case regex to any bit width (`\d+'b[01]+`), so the GA
  can mutate picorv32_alu's 4-bit opcode, not just alu_basic's 3-bit one.
- `2_evolutionary_engine/crossover_engine.py` -- same generalization.
- `1_symbolic_core/design_rule_checker.py` -- same generalization.
- `3_sandbox_time/testbench_generator.py` -- rewritten as a multi-module
  dispatch registry (`MODULE_RENDERERS`), alu_basic behavior unchanged
  and covered by the original 30 tests (still passing), picorv32_alu
  added following the extension pattern the repo already documented in
  `designs/seed/comparator_4bit.v`. `generate_vectors` kept as a
  backward-compat alias.
- `3_sandbox_time/yosys_synthesizer.py` -- **bug fix**: the `ltp` (logic
  depth) regex never matched real Yosys 0.33 output
  (`Longest topological path in <mod> (length=N):`), so `logic_depth` was
  silently always 0 for every design, alu_basic included. Fixed and
  verified (picorv32_alu: logic_depth=23).
- `2_evolutionary_engine/baseline_compare.py` -- rewritten: was dead code
  (never called from anywhere), had its own duplicate copy of the same
  broken ltp regex, and hardcoded `yosys` instead of a configurable
  binary. Now reuses the fixed regex, is CLI-usable, and writes JSON+MD
  reports. Tested for real against an actual GA output.
- `4_self_improve_loop/evolution_orchestrator.py` -- **bug fix**: run
  history was written to one shared `dashboard/run_history.json`
  regardless of `module_name`, so running a second module (e.g.
  picorv32_alu after alu_basic) silently corrupted the dashboard by
  mixing two runs with incompatible fitness scales into one file. Now
  per-module (`run_history_<module>.json`).
- `dashboard/app.py` -- updated to read the per-module history file
  matching the sidebar's module-name selector, falling back to the legacy
  shared file for old runs.
- `run_self_learner.py` -- added `--full-verify` flag to chain the full
  hardware verification pipeline after a GA run finishes.
- `README.md` -- new "Real Hardware Verification Flow" section with exact
  install/run commands for all 4 stages; updated "Current Limitations" and
  "Benchmarking" sections to match what's actually implemented now.

## What's real vs. what needs your machine

Tested for real, in the sandbox this was built in (results reproducible):
functional correctness (940/940 vectors), generic Yosys synthesis,
baseline_compare, nextpnr-ice40 P&R, the full pipeline's graceful
skip/report behavior, all 44 unit tests, a live 4-generation GA smoke run
on picorv32_alu.

Needs your WSL2/Linux machine (Docker + sky130 PDK + a compiled OpenSTA):
the OpenLane real-ASIC-area stage and the OpenSTA real-timing stage.
Exact install commands are in README.md's "Real Hardware Verification
Flow" section.
