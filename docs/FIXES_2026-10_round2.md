# Round 2: gaps A-H

| Item | Implemented | Where |
|---|---|---|
| A/E fitness | Uncapped relative-gain scoring (tie == 1.0), configurable weights, `improvement_pct` in reports; guard so `logic_depth == 0` is never read as a speedup. NOTE: the old formula was not actually capped at 1.0 -- 1.000 was the *tie with the seed* score, i.e. the search had found nothing better | `evolutionary_engine/fitness_evaluator.py` |
| B pass-guided mutation | `yosys_pass_pipeline` operator (composed prune/share/extract passes + `abc -g` gate-set swap) and 4 extra fixed recipes | `evolutionary_engine/resynth_operator.py` |
| C LEC | `verification_mode: formal/hybrid`; `check_equivalence_auto` (miter+SAT or equiv_make flow); `--selftest` against real Yosys | `sandbox/equivalence_checker.py`, `fitness_evaluator.py` |
| D islands | `IslandModel` + orchestrator integration + migration | `evolutionary_engine/islands.py`, `self_improve_loop/evolution_orchestrator.py` |
| F operators | 4 algebraic identity rewrites + the pass pipeline | `evolutionary_engine/algebraic_rewrites.py` |
| G speed | Formal proof skips Verilator; evaluation cache dedupes identical genomes | `fitness_evaluator.py`, orchestrator |
| H hierarchy | `design_bundle`, multi-file configs, auto `-sv`/flatten in synth + resynth + equivalence, example `designs/examples/hier_mac/` | `sandbox/design_bundle.py` |
| Bug found on the way | DRC `check_unconnected_output` mis-parsed `output logic [N:0] x` (took `logic` as the port name) and ignored outputs driven by sub-module ports, so every SystemVerilog/hierarchical genome would have been rejected before evaluation | `symbolic_core/design_rule_checker.py` |

Not done / open: yosys-slang frontend; real Verilog AST; hierarchical real-area (liberty) stage;
measuring any of the speed or area claims.
