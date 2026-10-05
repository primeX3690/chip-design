# Round 4: the "missing for real EDA" list -- what was built and what was deliberately not

Decision: build the logic-level kernel (everything verifiable offline), skip physical design.

| Missing item | Done | Verified how |
|---|---|---|
| HDL front-end / elaboration | `evohdl/eda/elaborate.py` (AST -> AIG, hierarchy, params, if/case, registers) | 3x fuzz of random expressions vs pysim (0 mismatches over 12 000 vectors after fixing 2 real semantic bugs it exposed in pysim's constant evaluation); all seeds cycle-by-cycle; hierarchy + parameter override tests |
| Netlist IR | `netlist.py` | mapped netlists simulated and converted back to AIG, then proven equivalent |
| Logic optimization, tech mapping, Liberty | `aig.py`, `opt.py`, `liberty.py`, `techmap.py`, `libs/tiny_generic.lib` | CEC proof on every pass/benchmark; mapper exact for area and delay objectives |
| STA + SDC | `sta.py` | hand-computed 3-inverter chain matches to 1e-9; SDC parsing, flop setup paths, violation detection tested |
| Own simulator / formal without Yosys | AIG simulator, `sat.py` (CDCL), `cec.py` (miter, latch-matched, BMC), native fallback in `formal_pipeline.py` | SAT vs brute force on 250 random CNFs + pigeonhole; counterexamples re-simulated; formal pipeline proves/refutes with Yosys absent |
| Benchmarks, regression DB, CLI | `benchmarks.py` (c17 exact + generators), `bench_io.py` (.bench/.aag), `regress.py`, `cli.py`, baseline DB | generators checked against Python reference functions; format round-trips proven |
| Power | `estimate_power` | scales with frequency, leakage constant |
| **Placement / routing / LEF / DEF / GDSII** | **not built** | needs a real PDK; toy placers would mislead. Use OpenLane |
| **Physical DRC / LVS** | **not built** | same |
| **Coverage metrics** | **not built** | |
| Real ISCAS-85 / EPFL / OpenCores | **not bundled** (no network); `bench run-dir` ingests them | |

Bugs found along the way (all fixed): pysim `Widths.const` silently evaluated non-constant expressions with signals = 0;
sized literals in constant expressions were not truncated; priority-encoder generator was wrong (caught by reference
check); `.bench` writer clashed on register-named outputs; netlist back-conversion duplicated the clock port.

Known weak spots: `balance` does not rebalance XOR chains; multiplier-class equivalence exceeds the pure-Python solver's
budget (reported as SIM_ONLY, never as proven); the bundled library is fictional.
