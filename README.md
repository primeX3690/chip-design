# EvoHDL — AI-Powered RTL Optimization Engine

EvoHDL is a self-improving hardware design system. It evolves Verilog RTL
using genetic programming, scoring every candidate design for **functional
correctness** (via Verilator simulation) and **area/timing efficiency**
(via Yosys synthesis) — automatically shrinking and speeding up a digital
circuit generation over generation, without a human hand-tuning the RTL.

This repository ships a working end-to-end reference implementation that
evolves an 8-bit ALU. The architecture generalizes to other combinational
and sequential blocks by swapping the seed design and testbench.

## Why this matters (for reviewers / investors / accelerators)

Chip design cycles are dominated by manual RTL iteration and synthesis
sweeps that senior engineers do by hand. EvoHDL is a proof-of-concept for
automating that inner loop with search + real EDA tool feedback instead of
a black-box neural net guessing at gate counts. The result is:

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
1_symbolic_core/       Static analysis: constraint extraction, DRC pre-filtering
2_evolutionary_engine/ Genetic programming: mutation, crossover, fitness, population
3_sandbox_time/        Sandboxed EDA tool execution: Verilator + Yosys via subprocess
4_self_improve_loop/   The orchestrator: the generation-by-generation GA loop
designs/               Seed design(s), per-generation populations, best-of-run
tests/                 pytest unit tests + testbench generation + golden ALU model
benchmarks/            Seed-vs-evolved comparison report generator
utils/                 Diff viewer + run-history-to-markdown summarizer
dashboard/             Streamlit live-monitoring UI
config/                All run parameters in one YAML file
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

35 tests cover the mutation operators, crossover, tournament/elite
selection, static DRC checks, and — most importantly — the golden ALU
reference model that every mutant's correctness is checked against. These
run without Verilator/Yosys installed (pure Python logic). CI
(`.github/workflows/ci.yml`) additionally installs the real toolchain and
runs a live 2-generation smoke test on every push.

## Benchmarking (for pitch decks / applications)

After a full run has produced `designs/best/`, generate a before/after
comparison table:

```bash
python benchmarks/benchmark_report.py --out benchmarks/report.md
```

See exactly what the algorithm changed:

```bash
python utils/verilog_diff.py
```

Turn a completed run into a paste-ready markdown summary:

```bash
python utils/report_generator.py --out RUN_SUMMARY.md
```

## Current Limitations

Being upfront about this matters more than overselling it:

- **Interface-fixed mutation.** Mutation and crossover only modify the
  *implementation* inside the fixed ALU port contract — they don't grow or
  shrink the interface, and they operate at statement/line granularity via
  regex rather than a full Verilog AST. This keeps the system reliable and
  dependency-light, but it bounds how structurally different a mutant can
  get from the seed. Swapping in a real Verilog parser (pyverilog, slang,
  or a Yosys-based AST dump) is the natural next step for exploring larger
  design-space jumps.
- **Generic synthesis target.** `yosys_synthesizer.py` uses the
  technology-independent `synth` pass, so area/delay are proxies (cell
  count, longest topological path) rather than numbers from a real
  standard-cell library or timing analysis (STA). Swap in `synth_<vendor>`
  and a real `.lib` file for silicon-accurate numbers.
- **Single design family.** The reference implementation targets one
  8-bit ALU. Extending to sequential circuits (state machines, pipelines)
  needs a testbench generator that drives a clock and checks state over
  multiple cycles, not just combinational input/output pairs.
- **No formal equivalence checking.** Correctness is established by
  simulation against ~350+ test vectors (corner cases + random), not formal
  verification. For safety-critical designs, add an equivalence check
  (e.g. Yosys `eqy`) between mutant and seed before accepting a "correct"
  result.


