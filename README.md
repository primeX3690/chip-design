# EvoHDL — Search-Based RTL Optimization Experiments

EvoHDL is an experiment in search-based RTL optimization. It mutates Verilog
with a genetic algorithm and scores every candidate for **functional
correctness** (Verilator simulation) and **area/timing proxies** (Yosys
synthesis). It is a thin orchestration layer on top of open-source EDA tools
(Yosys, Verilator, OpenLane, OpenSTA, nextpnr) -- it is not itself a synthesis,
place-and-route or timing engine.

## Current status (read this first)

- **No demonstrated optimization yet** (the 2026-10 upgrades below target this but are unmeasured). Best recorded runs: `picorv32_alu` 0.0%
  improvement (cells and depth unchanged), `alu_basic` about 3% on cell count.
  See [`benchmarks/STATUS.md`](benchmarks/STATUS.md) for exactly what is and is
  not measured, and `benchmarks/archive/` for the historical runs.
- **No real silicon numbers yet.** The OpenLane/sky130 and OpenSTA stages are
  implemented as wrappers but have never been run to completion.
- **Why the search stalls:** random text edits (operator swap, constant flip)
  change the design's meaning and almost always fail the correctness check,
  while an already-clean ALU leaves little for semantics-preserving edits to
  gain. See "Current Limitations".

Everything below describes what the code *can* do, not results it has achieved.

## Native EDA kernel (no external tools) -- new in the v4 release

`python -m evohdl.eda flow design.v --top m` runs a complete tool-independent flow: elaborate to an And-Inverter Graph,
optimize (rewrite / balance / SAT sweeping), **prove** the result equivalent with an in-house CDCL SAT solver, map onto a
Liberty library, prove the netlist equivalent again, then static timing (NLDM + SDC subset) and a power estimate.
The formal pipeline also uses it as a fallback, so a proof is possible on a machine with *no* Yosys at all.
Read [`docs/EDA_KERNEL.md`](docs/EDA_KERNEL.md) first -- it lists exactly what is and is not covered (physical design,
physical DRC/LVS, real benchmark suites and a real PDK library are **not** included; the bundled `.lib` is fictional).

## The commercial wedge and how to prove it (v5)

Chosen wedge (a hypothesis, not a validated market): a **formally verified optimization / equivalence layer on top of the
open-source flow**, for teams that cannot afford commercial licences. The proof tooling is in the repo:

- `python -m evohdl.eda compare --lib <real.lib>` (or `LIB=... bash scripts/run_head_to_head.sh`): head-to-head against Yosys+ABC
  on a suite, with the verified pre-pass, environment fingerprints and an auto-generated "what this does NOT show" section.
  Losses and unsupported designs are listed, and an unverified result is never counted as a win.
- `scripts/fpga_ice40_demo.sh`: same design through plain Yosys vs the verified pre-pass on iCE40, then place & route and a board.
- [`docs/WEDGE_PLAN.md`](docs/WEDGE_PLAN.md) (go/no-go gate, claims policy, investor checklist, India programme checklist) and
  [`docs/CUSTOMER_DISCOVERY.md`](docs/CUSTOMER_DISCOVERY.md). **No head-to-head result exists yet**: it needs a machine with Yosys.

## What changed in the 2026-10 upgrade (A-H)

All of these are implemented and unit-tested **with the EDA tools mocked**; none has been run end to end
against a real Yosys/Verilator yet (see `benchmarks/STATUS.md`). Run
`python -m evohdl.sandbox.equivalence_checker --selftest` and `python -m evohdl.sandbox.formal_pipeline --selftest` first.

| Area | What it is | Config |
|---|---|---|
| Fitness (A/E) | Uncapped relative gain: `1.0 + area_weight*cut + delay_weight*cut`; tie with seed == exactly 1.0 | `fitness_mode`, `area_weight`, `delay_weight` |
| Yosys pass-guided mutation (B) | `yosys_pass_pipeline` operator: random ordered subset of `wreduce/opt_expr/opt_muxtree/opt_reduce/peepopt/alumacc+share/opt_merge/opt_clean`, optional `extract_fa`/`extract_reduce`, and an `abc -g` gate-set swap; output is always valid Verilog | automatic (operator weights adapt) |
| Formal verification (C/G) | `hybrid`: Yosys equivalence vs the seed first (miter+SAT for combinational, `equiv_make/equiv_simple/equiv_induct` for sequential); proof skips Verilator, counterexample rejects, unproven falls back to simulation. Plus a per-run evaluation cache so identical genomes are never re-checked | `verification_mode`, `equiv_timeout_sec` |
| Island model (D) | Sub-populations with per-island mutation pressure, ring/random migration of best individuals | `islands`, `migration_*` |
| Structure-aware operators (F) | `commutative_swap`, `demorgan`, `sub_as_add`, `ternary_invert` (semantics-preserving identities) | automatic |
| Syntax-tree mutation | `evohdl/hdl/` parser+printer; 10 AST operators (`ast_commutative`, `ast_reassociate`, `ast_demorgan`, `ast_distribute`/factor, `ast_sub_as_add`, `ast_ternary_invert`, `ast_simplify`, `ast_if_ternary`, `ast_case_reorder`, `ast_cse`). Verified by differential pure-Python simulation (original vs mutant) on random stimulus | automatic |
| Sequential designs | `fsm_seqdet`, `mult_seq8` seeds + generic cycle-trace testbench + golden models; crossover understands FSM state labels | `config/config_fsm_seqdet.yaml`, `config/config_mult_seq8.yaml` |
| Automated formal pipeline | `formal_pipeline.py` (SAT miter / equiv_make / eqy / bounded BMC from reset), run automatically after every GA run, `--selftest` against real tools | `formal_depth`, `formal_timeout_sec`, `use_eqy`, `reset_port` |
| Hierarchy / SystemVerilog (H) | Multi-file seeds (`seed_files`), `include` inlining, top inference, auto `read_verilog -sv`, auto flatten, per-side flattening in the equivalence checker | `seed_files`, `module_name`, `include_dirs`; example `config/config_hier_mac.yaml` |

Caveats that matter: formal equivalence is relative to the *seed* (the orchestrator sanity-simulates the seed
if Verilator is present); SAT can time out on very wide arithmetic, and a timeout counts as "unproven", never as a pass;
SystemVerilog goes through Yosys' built-in frontend only (no interfaces/classes; yosys-slang is not integrated);
the liberty/real-area stage does not support multi-module designs yet; speedups are **not measured**.

## Design goals

The idea being tested: automate part of the manual RTL-iteration inner loop
with search plus real EDA tool feedback, rather than a learned proxy. The
design properties are:

- **Verifiable** — every candidate design is checked for bit-exact
  functional correctness before its area/delay is even considered, so the
  system cannot "cheat" its way to a smaller-but-wrong circuit.
- **Tool-grounded** — fitness comes from real Verilator/Yosys output, not
  a learned proxy, so results are trustworthy without a human re-checking
  every generation.
- **Explainable** — every genome's full mutation lineage is tracked
  (`gene_pool.Individual.mutation_history`), so you can trace exactly
  which changes produced a fitness gain.

This is presented as an early-stage R&D prototype, not a finished EDA
product — see "Current Limitations" below for what a production version
would still need.

## Architecture

```
evohdl/symbolic_core/       Static analysis: constraint extraction, DRC pre-filtering
evohdl/evolutionary_engine/ Genetic programming: mutation, crossover, fitness, population
evohdl/sandbox/        Sandboxed EDA tool execution: Verilator + Yosys via subprocess
evohdl/self_improve_loop/   The orchestrator: the generation-by-generation GA loop, plus
                        openlane_runner / opensta_runner / nextpnr_runner /
                        hardware_verification_pipeline (real-hardware verification)
flow/                  Real EDA tool configs/scripts: OpenLane (sky130), OpenSTA, nextpnr
designs/               Seed design(s) (alu_basic, picorv32_alu), per-generation
                        populations, best-of-run
tests/                 pytest unit tests + testbench generation + golden model(s)
benchmarks/            Seed-vs-evolved comparison + hardware verification reports
utils/                 Diff viewer + run-history-to-markdown summarizer
dashboard/             Streamlit live-monitoring UI
config/                All run parameters in one YAML file per module
.github/workflows/     CI: installs Verilator/Yosys and runs the test suite on every push
```

Data flow per generation:

```
seed design → [mutate / crossover] → candidate genome
                                          │
                                 design_rule_checker (fast static pre-filter)
                                          │
                                 verilator_sandbox (functional correctness)
                                          │
                                 yosys_synthesizer (area / logic depth)
                                          │
                                 fitness_evaluator (single scalar score)
                                          │
                                 gene_pool (tournament selection, elitism)
                                          │
                                 reward_backprop (adapts mutation mix)
                                          ▼
                                    next generation
```

## Environment Setup

EvoHDL orchestrates real EDA tools — they are **not** pip packages and must
be installed separately.

> **On Windows?** Native Windows doesn't run Verilator/Yosys reliably —
> use WSL2. Full step-by-step guide (including RAM-constrained-laptop
> tuning): **[WSL2_SETUP.md](WSL2_SETUP.md)**.

### 1. System dependencies

**Ubuntu / Debian**
```bash
sudo apt update
sudo apt install -y verilator yosys build-essential
```

**macOS (Homebrew)**
```bash
brew install verilator yosys
```

**From source** (if your distro's package is too old — EvoHDL needs
Verilator ≥ 4.2 and Yosys ≥ 0.20):
- Verilator: https://verilator.org/guide/latest/install.html
- Yosys: https://github.com/YosysHQ/yosys#building-from-source

Verify both are on your PATH:
```bash
verilator --version
yosys -V
```

### 2. Python environment

```bash
cd EvoHDL
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r config/requirements.txt
pip install -e .                 # makes the `evohdl` package importable
```

### 3. Sanity check before a full run

```bash
python run_self_learner.py --check-tools
```

## Usage

Run the evolutionary loop with default settings (24 individuals, 30
generations, defined in `config/system_config.yaml`):

```bash
python run_self_learner.py
```

Override parameters from the CLI without editing the config file:

```bash
python run_self_learner.py --generations 50 --population 32 --verbose
```

Evolve the real PicoRV32 ALU instead of the 8-bit teaching ALU:

```bash
python run_self_learner.py --config config/config_picorv32_alu.yaml --verbose
```

Watch it live in a second terminal:

```bash
streamlit run dashboard/app.py
```

Outputs:
- `designs/best/alu_basic_best.v` — best design found so far
- `designs/best/alu_basic_best_report.json` — its fitness breakdown
- `designs/gen_N/` — full population snapshot for every generation
- `dashboard/run_history.json` — fitness/diversity history for the dashboard

## Testing

```bash
pytest tests/unit/ -v
```

The unit tests cover the mutation operators, crossover, tournament/elite
selection, static DRC checks, Yosys output parsing, and the golden reference
models (ALU, PicoRV32 ALU, 4-bit counter) every mutant is checked against.
They run without Verilator/Yosys installed (pure Python logic, external tools
mocked); CI reports the current count. CI
(`.github/workflows/ci.yml`) additionally installs the real toolchain and
runs a live 2-generation smoke test on every push.

## Benchmarking

After a full run has produced `designs/best/`, generate a before/after
comparison table (fast, technology-independent Yosys proxy -- cell count +
logic depth):

```bash
python -m evohdl.evolutionary_engine.baseline_compare \
    --module picorv32_alu \
    --baseline designs/seed/picorv32_alu.v \
    --evolved designs/best/picorv32_alu_best.v \
    --out-json benchmarks/baseline_result.json \
    --out-md benchmarks/baseline_result.md
```

For real, silicon-referenced numbers (um^2 die area on the open SkyWater
130nm PDK, picosecond-accurate timing, routed FPGA congestion) instead of
the technology-independent proxy above, run the full hardware verification
pipeline -- see "Real Hardware Verification Flow" below.

See exactly what the algorithm changed:

```bash
python utils/verilog_diff.py
```

Turn a completed run into a paste-ready markdown summary:

```bash
python utils/report_generator.py --out RUN_SUMMARY.md
```

## Real Hardware Verification Flow

`alu_basic` and the generic `synth`-pass numbers above are useful for the
GA's per-generation fitness function (fast: milliseconds per individual),
but "cell count went down 12%" is a technology-independent proxy, not a
number a chip reviewer will accept at face value. This flow turns the GA's
best genome into real, tool-verified numbers, in four stages:

| Stage | Tool | What it proves | Runs on |
|---|---|---|---|
| 1. Seed design | Real PicoRV32 ALU (`designs/seed/picorv32_alu.v`) | The baseline is a real, silicon-proven core's RTL, not a toy strawman | n/a (source) |
| 2. Real ASIC area | OpenLane + SkyWater 130nm (`sky130_fd_sc_hd`) | Real die area in um^2, from an actual RTL-to-GDSII flow | Docker |
| 3. Real timing | OpenSTA + the sky130 liberty timing model | Real picosecond-accurate worst-case delay, not a logic-level count | OpenSTA binary |
| 4. Real FPGA P&R | nextpnr-ice40 (out-of-context, no board) | Real routed congestion + a real routed critical path | Laptop, no board |

Run all four in one shot after a GA run finishes:

```bash
python run_self_learner.py --config config/config_picorv32_alu.yaml --full-verify
```

or standalone, against any baseline/evolved pair:

```bash
python -m evohdl.self_improve_loop.hardware_verification_pipeline \
    --module picorv32_alu \
    --baseline designs/seed/picorv32_alu.v \
    --evolved designs/best/picorv32_alu_best.v
```

This writes `benchmarks/hardware_verification_report.md` (and a `.json`
twin). Any stage whose tool isn't installed is clearly marked
"Not available" in the report with the reason -- it is never faked or
silently skipped without saying so.

### Low-RAM laptops (8GB / Ryzen 3 class): skip Docker locally, use CI instead

OpenLane's Docker image alone typically wants 4-6 GB of RAM while it
runs -- tight-to-unworkable on an 8GB laptop that's also running the OS,
a browser, etc. `.github/workflows/hardware_verification.yml` runs the
same OpenLane + sky130 flow on GitHub's free `ubuntu-latest` runner
(2 vCPU, 7 GB RAM) instead, so your laptop never has to run Docker at all:

1. Push `designs/best/<module>_best.v` to GitHub (already covered by the
   normal `git push` at the end of a run).
2. Go to the repo's **Actions** tab -> **EvoHDL Real Hardware
   Verification (OpenLane + sky130)** -> **Run workflow** -> enter the
   module name (e.g. `picorv32_alu`) -> **Run workflow**.
3. When it finishes (~15-30 min for a small module), download the
   `hardware-verification-report-<module>` artifact from the run page --
   it contains the same `hardware_verification_report.md` /`.json` that a
   local `--full-verify` run would produce, with real sky130 die area and
   real timing slack numbers.

Stage 4 (nextpnr-ice40) is light enough to keep running locally --
`apt install nextpnr-ice40` and `python -m evohdl.self_improve_loop.nextpnr_runner designs/seed/picorv32_alu.v
picorv32_alu` both run fine on an 8GB laptop (verified: this exact command
completes in a few seconds).

### Setup per stage

**Stage 4 (nextpnr-ice40) -- easiest, do this first:**

```bash
sudo apt-get update && sudo apt-get install -y yosys nextpnr-ice40
python -m evohdl.self_improve_loop.nextpnr_runner designs/seed/picorv32_alu.v picorv32_alu
```

**Stage 2 (OpenLane + SkyWater 130nm) -- needs Docker:**

```bash
# Docker Desktop (Windows/WSL2) or Docker Engine (native Linux) must be
# running first. Then:
pip install --user volare
volare enable --pdk sky130 $(volare ls-remote --pdk sky130 | tail -1)   # pulls the PDK once, ~2-3 GB
python -m evohdl.self_improve_loop.openlane_runner designs/seed/picorv32_alu.v picorv32_alu
```

**Stage 3 (OpenSTA) -- build from source (not packaged for apt/pip):**

```bash
git clone --recursive https://github.com/parallaxsw/OpenSTA.git
cd OpenSTA && mkdir build && cd build
cmake .. && make -j$(nproc)
sudo make install   # installs the `sta` binary
cd ../..
python -m evohdl.self_improve_loop.opensta_runner \
    <path-to-openlane-routed-netlist> picorv32_alu \
    --pdk-root ~/.volare
```

(Stage 3 reads whichever sky130 liberty file Stage 2's PDK download
already placed under `~/.volare` -- it does not download the PDK a second
time.)

## Current Limitations

Being upfront about this matters more than overselling it:

- **Interface-fixed mutation.** Mutation and crossover only modify the *implementation* inside a module's
  fixed port contract; they never grow or shrink the interface. Structure-aware rewrites now run on a real
  syntax tree (`evohdl/hdl/`, a pure-Python parser/printer for a Verilog-2001 + SystemVerilog subset: modules,
  ports, parameters, wire/reg/logic, assign, always*/begin/if/case, all expression forms, instances). It does
  **not** cover `generate`, functions/tasks, `initial`, loops, interfaces, packages or structs; on such sources the
  AST operators fall back to the older regex operators or no-op. This is our own parser, not PyVerilog or slang
  (neither could be installed where this was developed); an adapter for slang/pyverilog is a possible later step.
  At startup `analyze_design_support()` logs what a seed will not support.
- **Generic synthesis is still the per-generation fitness signal.**
  `yosys_synthesizer.py` uses the technology-independent `synth` pass for
  speed across hundreds of individuals x dozens of generations — area/
  delay from that pass are proxies (cell count, longest topological path),
  not real silicon numbers. The "Real Hardware Verification Flow" above
  runs the real OpenLane/sky130 + OpenSTA + nextpnr-ice40 tools on the
  *single best* genome once a run finishes, rather than on every
  individual, which is what keeps the search itself fast while still
  producing investor-credible final numbers.
- **Five registered designs.** Combinational: `alu_basic`, `picorv32_alu`. Sequential: `counter_4bit`,
  `fsm_seqdet` (Moore FSM, 1011 detector) and `mult_seq8` (multi-cycle 8x8 shift-add multiplier, 8-cycle latency).
  Sequential designs use a generic cycle-trace Verilator testbench driven by spec-level golden models
  (`testbench_generator.py`); the seeds were checked against those models by pure-Python simulation and the
  generated C++ testbenches were compiled and run against C++ stand-ins of the seeds, but **none has been run
  through Verilator or the GA with real tools yet**. `comparator_4bit.v` still has a seed but no renderer. Adding a
  design means adding a renderer to `MODULE_RENDERERS`.
- **Formal verification: what "proven" means.** Every run now ends with an automatic proof attempt of best vs seed
  (`evohdl/sandbox/formal_pipeline.py`, report in `benchmarks/formal_proof_<module>.md`): Yosys miter+SAT for
  combinational designs, `equiv_make`+`equiv_simple`+`equiv_induct` for sequential ones (unbounded when it works),
  optional YosysHQ `eqy`, then a bounded model check from reset as the last resort. The report names the strongest
  thing actually shown (`PROVEN_UNBOUNDED`, `PROVEN_BY_EQY`, `PROVEN_BOUNDED` for N cycles, `NOT_EQUIVALENT`,
  `UNPROVEN`). It is equivalence to the *seed* under Yosys' semantics with a trusted solver -- not a proof the
  seed is right, and a sequential design with re-encoded state will often only reach `PROVEN_BOUNDED`.
  During the GA itself, `hybrid`/`formal` modes use the same checkers per candidate.
- **Stages 2-3 of the hardware verification flow need external
  toolchains** (Docker + the sky130 PDK; a from-source OpenSTA build) that
  aren't part of this repo's pip requirements, by design — they're
  multi-GB EDA toolchains, not Python packages. Stages 1 and 4 need only
  `apt install yosys verilator nextpnr-ice40` and run standalone.




