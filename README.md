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
4_self_improve_loop/   The orchestrator: the generation-by-generation GA loop, plus
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

35 tests cover the mutation operators, crossover, tournament/elite
selection, static DRC checks, and — most importantly — the golden ALU
reference model that every mutant's correctness is checked against. These
run without Verilator/Yosys installed (pure Python logic). CI
(`.github/workflows/ci.yml`) additionally installs the real toolchain and
runs a live 2-generation smoke test on every push.

## Benchmarking (for pitch decks / applications)

After a full run has produced `designs/best/`, generate a before/after
comparison table (fast, technology-independent Yosys proxy -- cell count +
logic depth):

```bash
python 2_evolutionary_engine/baseline_compare.py \
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
python 4_self_improve_loop/hardware_verification_pipeline.py \
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
`apt install nextpnr-ice40` and `python
4_self_improve_loop/nextpnr_runner.py designs/seed/picorv32_alu.v
picorv32_alu` both run fine on an 8GB laptop (verified: this exact command
completes in a few seconds).

### Setup per stage

**Stage 4 (nextpnr-ice40) -- easiest, do this first:**

```bash
sudo apt-get update && sudo apt-get install -y yosys nextpnr-ice40
python 4_self_improve_loop/nextpnr_runner.py designs/seed/picorv32_alu.v picorv32_alu
```

**Stage 2 (OpenLane + SkyWater 130nm) -- needs Docker:**

```bash
# Docker Desktop (Windows/WSL2) or Docker Engine (native Linux) must be
# running first. Then:
pip install --user volare
volare enable --pdk sky130 $(volare ls-remote --pdk sky130 | tail -1)   # pulls the PDK once, ~2-3 GB
python 4_self_improve_loop/openlane_runner.py designs/seed/picorv32_alu.v picorv32_alu
```

**Stage 3 (OpenSTA) -- build from source (not packaged for apt/pip):**

```bash
git clone --recursive https://github.com/parallaxsw/OpenSTA.git
cd OpenSTA && mkdir build && cd build
cmake .. && make -j$(nproc)
sudo make install   # installs the `sta` binary
cd ../..
python 4_self_improve_loop/opensta_runner.py \
    <path-to-openlane-routed-netlist> picorv32_alu \
    --pdk-root ~/.volare
```

(Stage 3 reads whichever sky130 liberty file Stage 2's PDK download
already placed under `~/.volare` -- it does not download the PDK a second
time.)

## Current Limitations

Being upfront about this matters more than overselling it:

- **Interface-fixed mutation.** Mutation and crossover only modify the
  *implementation* inside a module's fixed port contract — they don't grow
  or shrink the interface, and they operate at statement/line granularity
  via regex (generalized to any bit-width case selector, not just 3-bit,
  as of the picorv32_alu integration) rather than a full Verilog AST. This
  keeps the system reliable and dependency-light, but it bounds how
  structurally different a mutant can get from the seed. Swapping in a
  real Verilog parser (pyverilog, slang, or a Yosys-based AST dump) is the
  natural next step for exploring larger design-space jumps.
- **Generic synthesis is still the per-generation fitness signal.**
  `yosys_synthesizer.py` uses the technology-independent `synth` pass for
  speed across hundreds of individuals x dozens of generations — area/
  delay from that pass are proxies (cell count, longest topological path),
  not real silicon numbers. The "Real Hardware Verification Flow" above
  runs the real OpenLane/sky130 + OpenSTA + nextpnr-ice40 tools on the
  *single best* genome once a run finishes, rather than on every
  individual, which is what keeps the search itself fast while still
  producing investor-credible final numbers.
- **Two design families so far.** `alu_basic` (8-bit teaching ALU) and
  `picorv32_alu` (real 32-bit RV32I ALU extracted from PicoRV32, see
  `designs/seed/picorv32_alu.v`). Extending to sequential circuits (state
  machines, pipelines, PicoRV32's multi-cycle multiplier/divider) needs a
  testbench generator that drives a clock and checks state over multiple
  cycles, not just combinational input/output pairs — `comparator_4bit.v`
  and `counter_4bit.v` are left as the next extension points, following
  the dispatch-registry pattern in `3_sandbox_time/testbench_generator.py`.
- **No formal equivalence checking.** Correctness is established by
  simulation against ~350-950+ test vectors depending on module (corner
  cases + random), not formal verification. For safety-critical designs,
  add an equivalence check (e.g. Yosys `eqy`) between mutant and seed
  before accepting a "correct" result.
- **Stages 2-3 of the hardware verification flow need external
  toolchains** (Docker + the sky130 PDK; a from-source OpenSTA build) that
  aren't part of this repo's pip requirements, by design — they're
  multi-GB EDA toolchains, not Python packages. Stages 1 and 4 need only
  `apt install yosys verilator nextpnr-ice40` and run standalone.




