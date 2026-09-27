"""
fitness_evaluator.py
-----------------------
Combines simulation (correctness) and synthesis (area/delay) results into a
single scalar fitness value the GA can rank on.

Fitness philosophy:
  - Correctness dominates. A design that fails even one test vector is
    capped far below any fully-correct design, regardless of how small it
    synthesizes to (otherwise the GA will "cheat" by evolving a tiny,
    broken ALU).
  - Among fully-correct designs, smaller area and lower logic depth score
    higher, weighted per config/system_config.yaml.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "3_sandbox_time"))
from verilator_sandbox import evaluate_design, SimulationOutcome  # noqa: E402
from yosys_synthesizer import synthesize_design, SynthesisOutcome  # noqa: E402
from tech_aware_synthesizer import synthesize_tech_mapped, liberty_available  # noqa: E402

CORRECTNESS_FLOOR = 0.0      # fitness for a design that fails to compile at all
BROKEN_CEILING = 0.4         # max fitness a functionally-incorrect-but-compiling design can reach
CORRECT_BASE = 0.5           # fitness floor once functionally correct
AREA_WEIGHT = 0.30
DELAY_WEIGHT = 0.20

# Rough normalization anchors -- tuned against the ~10-cell / depth-3 seed ALU.
# Designs referencing config can override these via system_config.yaml.
BASELINE_CELLS = 40
BASELINE_DEPTH = 6


@dataclass
class FitnessReport:
    fitness: float
    functionally_correct: bool
    pass_ratio: float
    cell_count: int
    logic_depth: int
    sim_error: str
    synth_error: str
    real_area_um2: float = 0.0     # Stage-5 addition: real sky130-mapped area (0.0 = not measured)
    baseline_real_area_um2: float = 0.0

    def as_dict(self):
        return asdict(self)


def score(
    verilog_source: str,
    module_name: str = "alu_basic",
    verilator_bin: str = "verilator",
    yosys_bin: str = "yosys",
    baseline_cells: int = BASELINE_CELLS,
    baseline_depth: int = BASELINE_DEPTH,
    sim_timeout: float = 20.0,
    synth_timeout: float = 30.0,
    liberty_path: str | None = None,
    real_area_weight: float = 0.25,
    baseline_real_area_um2: float = 0.0,
) -> FitnessReport:
    sim: SimulationOutcome = evaluate_design(
        verilog_source, module_name=module_name, verilator_bin=verilator_bin, timeout_sec=sim_timeout
    )

    if not sim.compiled:
        return FitnessReport(
            fitness=CORRECTNESS_FLOOR,
            functionally_correct=False,
            pass_ratio=0.0,
            cell_count=0,
            logic_depth=0,
            sim_error=sim.error,
            synth_error="skipped (compile failed)",
        )

    if not sim.functionally_correct:
        # Reward partial correctness a little so the GA has gradient to climb,
        # but never let a broken design outrank a correct one.
        fitness = sim.pass_ratio * BROKEN_CEILING
        return FitnessReport(
            fitness=fitness,
            functionally_correct=False,
            pass_ratio=sim.pass_ratio,
            cell_count=0,
            logic_depth=0,
            sim_error=sim.error or "functional mismatch on one or more vectors",
            synth_error="skipped (not functionally correct)",
        )

    synth: SynthesisOutcome = synthesize_design(
        verilog_source, module_name=module_name, yosys_bin=yosys_bin, timeout_sec=synth_timeout
    )

    if not synth.synthesized:
        # Functionally correct but un-synthesizable is still better than broken,
        # but we can't reward area/delay we couldn't measure.
        return FitnessReport(
            fitness=CORRECT_BASE,
            functionally_correct=True,
            pass_ratio=1.0,
            cell_count=0,
            logic_depth=0,
            sim_error="",
            synth_error=synth.error,
        )

    # Lower is better for both -> convert to a "smaller is higher score" ratio.
    # IMPROVEMENT (2026-09): the old code clamped this ratio at 1.0, so once a
    # mutant merely matched the baseline (ratio == 1.0), shrinking it further
    # gave ZERO extra fitness -- the search had no incentive to keep improving
    # past "as good as the human-written seed". Only the floor (never go
    # negative for a wildly worse design) is kept; the ceiling is now a
    # generous soft cap (5x baseline) instead of 1.0, so genuinely smaller/
    # faster mutants keep being rewarded for going below the baseline too.
    area_score = max(0.0, min(5.0, baseline_cells / max(synth.cell_count, 1)))
    delay_score = max(0.0, min(5.0, baseline_depth / max(synth.logic_depth, 1)))

    fitness = CORRECT_BASE + AREA_WEIGHT * area_score + DELAY_WEIGHT * delay_score

    real_area_um2 = 0.0
    # Stage-5 addition (2026-09): optional real standard-cell-library-mapped
    # area (see tech_aware_synthesizer.py). Opt-in via config's
    # `liberty_path` -- if not set, behaves EXACTLY as before this change.
    # This is the metric that actually differentiates from "generic gate-
    # count proxy": two designs can tie on cell_count above yet differ here.
    if liberty_available(liberty_path):
        tech = synthesize_tech_mapped(
            verilog_source, module_name=module_name,
            liberty_path=liberty_path, yosys_bin=yosys_bin, timeout_sec=synth_timeout,
        )
        if tech.synthesized:
            real_area_um2 = tech.real_area_um2
            if baseline_real_area_um2 > 0:
                real_area_score = max(0.0, min(5.0, baseline_real_area_um2 / max(real_area_um2, 0.01)))
                fitness += real_area_weight * real_area_score
        # If tech-mapping fails (e.g. mutant doesn't map cleanly), we simply
        # don't add the bonus term rather than penalizing or crashing --
        # this stage is additive, informational, and must never make an
        # otherwise-correct design score worse than before this feature existed.

    return FitnessReport(
        fitness=fitness,
        functionally_correct=True,
        pass_ratio=1.0,
        cell_count=synth.cell_count,
        logic_depth=synth.logic_depth,
        sim_error="",
        synth_error="",
        real_area_um2=real_area_um2,
        baseline_real_area_um2=baseline_real_area_um2,
    )


if __name__ == "__main__":
    seed_path = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    report = score(seed_path.read_text())
    print(report)

