"""
fitness_evaluator.py
-----------------------
Combines a correctness verdict (formal equivalence and/or simulation) with
synthesis results (area/delay) into one scalar fitness the GA ranks on.

Fitness philosophy:
  - Correctness dominates. A design that is not proven/simulated correct is
    capped far below any correct design, whatever it synthesizes to.
  - Among correct designs, `fitness_mode="relative_gain"` (default) scores the
    fractional reduction vs the seed baseline, with NO artificial ceiling:

        fitness = 1.0 + area_weight  * (base_cells - cells) / base_cells
                      + delay_weight * (base_depth - depth) / base_depth
                      + real_area_weight * (base_um2 - um2) / base_um2   (only if measured)

    A design tied with the seed scores exactly 1.0 (that is "no improvement", not a cap),
    every extra % of area/delay removed adds linearly, and a worse-than-seed design is floored at
    CORRECT_BASE (still above any incorrect one). `legacy_ratio` keeps the old
    0.5 + w*baseline/value form (soft-capped at 5x) for comparing against older runs.

Verification modes (see sandbox/equivalence_checker.py):
  - simulation (default here): Verilator vectors only (needs a registered testbench).
  - formal: Yosys equivalence vs the seed; anything not PROVEN equivalent is not correct.
  - hybrid: formal first; a proof skips simulation, a counterexample rejects, inconclusive /
    sequential-unproven falls back to simulation.
  Formal modes assume the seed itself is correct (the orchestrator sanity-simulates it at start).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from evohdl.sandbox.verilator_sandbox import evaluate_design, SimulationOutcome  # noqa: E402
from evohdl.sandbox.yosys_synthesizer import synthesize_design, SynthesisOutcome  # noqa: E402
from evohdl.sandbox.tech_aware_synthesizer import synthesize_tech_mapped, liberty_available  # noqa: E402
from evohdl.sandbox.equivalence_checker import check_equivalence_auto  # noqa: E402
from evohdl.paths import SEED_DIR

CORRECTNESS_FLOOR = 0.0      # fitness for a design that fails to compile at all
BROKEN_CEILING = 0.4         # max fitness a functionally-incorrect-but-compiling design can reach
CORRECT_BASE = 0.5           # fitness floor once functionally correct
AREA_WEIGHT = 0.30           # legacy_ratio mode only
DELAY_WEIGHT = 0.20          # legacy_ratio mode only
REL_AREA_WEIGHT = 2.0        # relative_gain mode defaults (override via config area_weight/delay_weight)
REL_DELAY_WEIGHT = 1.0
NONEQUIV_FITNESS = 0.1       # formal counterexample found (no partial-credit gradient exists for formal)
UNPROVEN_FITNESS = 0.2       # formal mode: compiled but equivalence could not be proven

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
    real_area_measured: bool = False   # False => real_area_um2 == 0.0 means "not measured", not "zero area"
    verified_by: str = "simulation"    # "simulation" | "formal" | "formal+simulation(fallback)" | "none"
    area_improvement_pct: float = 0.0  # vs baseline_cells, positive = smaller
    delay_improvement_pct: float = 0.0 # vs baseline_depth, positive = shallower

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
    *,
    area_weight: float | None = None,
    delay_weight: float | None = None,
    fitness_mode: str = "relative_gain",
    verification_mode: str = "simulation",
    seed_source: str | None = None,
    equiv_timeout: float = 30.0,
) -> FitnessReport:
    verified_by = "simulation"
    formal_active = verification_mode in ("formal", "hybrid") and seed_source is not None
    sim = None

    if formal_active:
        eq = check_equivalence_auto(seed_source, verilog_source, module_name,
                                    yosys_bin=yosys_bin, timeout_sec=equiv_timeout)
        if eq.checked and eq.equivalent and not eq.bounded:
            verified_by = "formal"
        elif eq.checked and not eq.equivalent and eq.error:
            # a real counterexample: provably NOT the same function as the seed
            return FitnessReport(
                fitness=NONEQUIV_FITNESS, functionally_correct=False, pass_ratio=0.0,
                cell_count=0, logic_depth=0, sim_error=f"formal: {eq.error}",
                synth_error="skipped (not equivalent)", verified_by="formal",
            )
        elif verification_mode == "formal":
            proven_failed = eq.checked  # ran but could not prove
            return FitnessReport(
                fitness=UNPROVEN_FITNESS if proven_failed else CORRECTNESS_FLOOR,
                functionally_correct=False, pass_ratio=0.0, cell_count=0, logic_depth=0,
                sim_error=("formal: equivalence not proven (inconclusive)" if proven_failed
                           else f"formal: {eq.error or 'checker did not run'}"),
                synth_error="skipped (not proven equivalent)", verified_by="formal",
            )
        else:
            verified_by = "formal+simulation(fallback)"

    if verified_by == "formal":
        pass  # proven equivalent to the seed: skip the expensive Verilator compile + run
    else:
        sim = evaluate_design(
            verilog_source, module_name=module_name, verilator_bin=verilator_bin, timeout_sec=sim_timeout
        )

    if sim is not None and not sim.compiled:
        return FitnessReport(
            fitness=CORRECTNESS_FLOOR,
            functionally_correct=False,
            pass_ratio=0.0,
            cell_count=0,
            logic_depth=0,
            sim_error=sim.error,
            synth_error="skipped (compile failed)",
        )

    if sim is not None and not sim.functionally_correct:
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

    # Fractional reductions vs the seed baseline. Guard: a logic depth of 0 means `ltp` printed nothing
    # (or the design is pure wiring) -- never read that as "100% faster".
    area_gain = (baseline_cells - synth.cell_count) / baseline_cells if baseline_cells > 0 else 0.0
    if synth.logic_depth > 0 and baseline_depth > 0:
        delay_gain = (baseline_depth - synth.logic_depth) / baseline_depth
    else:
        delay_gain = 0.0

    if fitness_mode == "legacy_ratio":
        area_score = max(0.0, min(5.0, baseline_cells / max(synth.cell_count, 1)))
        delay_score = max(0.0, min(5.0, baseline_depth / max(synth.logic_depth, 1)))
        fitness = CORRECT_BASE + AREA_WEIGHT * area_score + DELAY_WEIGHT * delay_score
    else:
        aw = REL_AREA_WEIGHT if area_weight is None else area_weight
        dw = REL_DELAY_WEIGHT if delay_weight is None else delay_weight
        fitness = max(CORRECT_BASE, 1.0 + aw * area_gain + dw * delay_gain)

    real_area_um2 = 0.0
    real_area_measured = False
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
            real_area_measured = True
            if baseline_real_area_um2 > 0:
                if fitness_mode == "legacy_ratio":
                    real_area_score = max(0.0, min(5.0, baseline_real_area_um2 / max(real_area_um2, 0.01)))
                    fitness += real_area_weight * real_area_score
                else:
                    fitness += real_area_weight * (baseline_real_area_um2 - real_area_um2) / baseline_real_area_um2
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
        real_area_measured=real_area_measured,
        verified_by=verified_by,
        area_improvement_pct=round(area_gain * 100, 3),
        delay_improvement_pct=round(delay_gain * 100, 3),
    )


if __name__ == "__main__":
    seed_path = SEED_DIR / "alu_basic.v"
    report = score(seed_path.read_text())
    print(report)
