# Round 3: sequential designs, syntax-tree mutation, automated formal pipeline

| Request | What was done | What is verified, and how | Still open |
|---|---|---|---|
| Counter / FSM / multi-cycle multiplier support | New seeds `fsm_seqdet.v` (Moore FSM) and `mult_seq8.v` (8-cycle shift-add multiplier); generic cycle-trace Verilator testbench; spec-level golden models (state-encoding independent; multiplier checks latency + done-cycle result only); crossover learns FSM state labels; configs `config_fsm_seqdet.yaml`, `config_mult_seq8.yaml`; DRC/preflight accept them | Seeds simulated in pure Python against the golden models (FSM 3000 cycles, multiplier 4000 cycles): 0 mismatches. Generated C++ testbenches compiled with g++ -Wall and run against hand-written C++ stand-ins: 200/200 and 400/400 | Run through real Verilator + GA; larger FSMs / memory controllers |
| PyVerilog / slang style syntax-tree parser | Own pure-Python parser + printer + simulator (`evohdl/hdl/`), because neither PyVerilog nor slang could be installed here. 10 AST mutation operators acting on arbitrary sub-expressions | Round-trip (parse -> print -> parse equal, printing idempotent) on every seed; every operator differentially simulated original-vs-mutant on random inputs (comb + sequential seeds + a hand-written stress module); 25-step operator chains stay behaviour-equivalent | `generate`, functions, loops, interfaces, packages unsupported (regex fallback / no-op); slang/pyverilog adapter; width-aware area-saving rewrites (e.g. adder sharing) |
| Automated formal pipeline (eqy) | `formal_pipeline.py`: SAT miter -> equiv_make/induct -> optional eqy -> bounded BMC from reset; runs after every GA run; honest status vocabulary; hardware pipeline stage 0 now uses it; `async2sync` + `dffunmap` added to the sequential SAT script (needed for async-reset/enable flops) | Orchestration/decision logic and report text unit-tested with mocked tools; eqy config generation tested | **The Yosys/eqy script text is untested against real tools.** Run `python -m evohdl.sandbox.formal_pipeline --selftest` (8 cases) |

"100% mathematically proven" is only claimed where the method gives it (combinational SAT, successful equiv_induct).
Everything else is reported as bounded or unproven, by name.

Bug found while doing this: the old sequential SAT script lacked `async2sync`/`dffunmap`, so `sat` would have rejected the
async-reset counter outright.
