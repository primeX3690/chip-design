"""
evolution_orchestrator.py
-----------------------------
The GA "God Loop": for each generation --
  1. Evaluate fitness of every individual not yet scored (parallelizable).
  2. Log stats + persist the generation's best genome to disk.
  3. Select parents (tournament), apply crossover + mutation to breed
     the next generation, always carrying forward N elites unchanged.
  4. Feed fitness deltas into reward_backprop to bias next generation's
     mutation operator mix.

Designed to be resumable: every generation's population and best design are
written to designs/gen_N/ and designs/best/, and run history to a JSON log
the dashboard reads.
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "2_evolutionary_engine"))
sys.path.append(str(PROJECT_ROOT / "4_self_improve_loop"))
sys.path.append(str(PROJECT_ROOT / "1_symbolic_core"))

from gene_pool import GenePool, Individual  # noqa: E402
from verilog_mutator import mutate, configure_resynth  # noqa: E402
from crossover_engine import crossover  # noqa: E402
from fitness_evaluator import score  # noqa: E402
from design_rule_checker import run_all_checks  # noqa: E402
from design_generator import load_seed_design, generate_initial_population  # noqa: E402
from reward_backprop import OperatorCredit  # noqa: E402
from multi_objective import export_pareto_front_csv

logger = logging.getLogger("EvoHDL.orchestrator")


class EvolutionOrchestrator:
    def __init__(self, config: dict):
        self.config = config
        self.rng = random.Random(config.get("random_seed", 42))
        self.pool = GenePool(rng=self.rng)
        self.credit = OperatorCredit()
        self.operator_weights: List[float] | None = None
        self.history: List[dict] = []

        self.module_name = config.get("module_name", "alu_basic")
        self.population_size = config.get("population_size", 20)
        self.generations = config.get("generations", 30)
        self.elite_count = max(1, config.get("elite_count", 2))
        self.tournament_k = config.get("tournament_k", 3)
        self.crossover_rate = config.get("crossover_rate", 0.6)
        self.mutation_rate = config.get("mutation_rate", 0.8)
        self.max_workers = config.get("max_parallel_evals", 4)

        self.verilator_bin = config.get("verilator_bin", "verilator")
        self.yosys_bin = config.get("yosys_bin", "yosys")

        # BUG FIX (2026-09): these were computed by run_self_learner.py's
        # apply_auto_baseline() and written into `config`, but never actually
        # read here -- score() always fell back to fitness_evaluator.py's
        # hardcoded BASELINE_CELLS=40 / BASELINE_DEPTH=6 (tuned for the tiny
        # alu_basic teaching ALU). For picorv32_alu (1409 real cells), that
        # made area_score = 40/1409 = 0.028 -- almost zero gradient -- which
        # is why 30-40 generations of GA search never found a single smaller
        # variant (confirmed: benchmarks/hardware_verification_report.md
        # showed baseline == evolved, 1409 == 1409). Now module-aware.
        self.baseline_cells = config.get("baseline_cells", 40)
        self.baseline_depth = config.get("baseline_depth", 6)
        self.sim_timeout = config.get("sim_timeout_sec", 20.0)
        self.synth_timeout = config.get("synth_timeout_sec", 30.0)

        # Stage-5 addition (2026-09): optional real standard-cell-library
        # (e.g. sky130) area target -- see tech_aware_synthesizer.py's
        # docstring. Entirely opt-in: if `liberty_path` is unset in config,
        # every one of these is unused and behavior is identical to before.
        self.liberty_path = config.get("liberty_path")
        self.real_area_weight = config.get("real_area_weight", 0.25)
        self.baseline_real_area_um2 = config.get("baseline_real_area_um2", 0.0)

        self.designs_dir = PROJECT_ROOT / "designs"
        # NOTE: fixed 2026-09 -- this used to be a single shared
        # dashboard/run_history.json regardless of module_name, so running
        # e.g. picorv32_alu after alu_basic silently mixed two runs'
        # incompatible fitness scales into one file and corrupted the
        # dashboard. Now per-module; dashboard/app.py picks the most
        # recently modified one (see its module selector).
        self.log_path = PROJECT_ROOT / "dashboard" / f"run_history_{self.module_name}.json"

    # ---------------------------------------------------------------- setup

    def bootstrap(self):
        # Stage-6 addition (2026-09): resynth_alt_strategy needs to know
        # which module/yosys binary to resynthesize against -- must be set
        # before ANY mutation happens, including the diversifying mutations
        # generate_initial_population() applies below.
        configure_resynth(self.module_name, self.yosys_bin, self.synth_timeout)

        seed_path = PROJECT_ROOT / self.config.get("seed_design", "designs/seed/alu_basic.v")
        seed_source = load_seed_design(seed_path)
        drc = run_all_checks(seed_source)
        if not drc.passed:
            logger.warning("Seed design has static DRC warnings: %s", drc.violations)

        genomes = generate_initial_population(
            seed_source, self.population_size, diversify_mutations=1, rng=self.rng
        )
        self.pool.seed(genomes[0], 0, generation=0)
        self.pool.population = [
            Individual(genome=g, generation=0) for g in genomes
        ]
        logger.info("Bootstrapped population of %d from seed design.", len(self.pool.population))

    # ------------------------------------------------------------- evaluate

    def _evaluate_one(self, individual: Individual) -> Individual:
        if individual.fitness_report is not None:
            return individual  # already scored (elite carried forward)

        drc = run_all_checks(individual.genome)
        if not drc.passed:
            # Skip the expensive compile step for statically-broken genomes.
            from fitness_evaluator import FitnessReport
            individual.fitness_report = FitnessReport(
                fitness=0.0, functionally_correct=False, pass_ratio=0.0,
                cell_count=0, logic_depth=0,
                sim_error=f"DRC failed: {'; '.join(drc.violations)}",
                synth_error="skipped (DRC failed)",
            )
            return individual

        report = score(
            individual.genome,
            module_name=self.module_name,
            verilator_bin=self.verilator_bin,
            yosys_bin=self.yosys_bin,
            baseline_cells=self.baseline_cells,
            baseline_depth=self.baseline_depth,
            sim_timeout=self.sim_timeout,
            synth_timeout=self.synth_timeout,
            liberty_path=self.liberty_path,
            real_area_weight=self.real_area_weight,
            baseline_real_area_um2=self.baseline_real_area_um2,
        )
        individual.fitness_report = report
        return individual

    def evaluate_population(self):
        unscored = [ind for ind in self.pool.population if ind.fitness_report is None]
        if not unscored:
            return
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._evaluate_one, ind): ind for ind in unscored}
            for future in as_completed(futures):
                future.result()  # exceptions surface here if any slip through

    # -------------------------------------------------------------- breed

    def _breed_child(self, generation: int) -> tuple[Individual, str]:
        parent_a = self.pool.tournament_select(self.tournament_k)
        genome = parent_a.genome
        operator_kind = "none"

        if self.rng.random() < self.crossover_rate and len(self.pool.population) > 1:
            parent_b = self.pool.tournament_select(self.tournament_k)
            genome = crossover(parent_a.genome, parent_b.genome, self.rng).child_source

        if self.rng.random() < self.mutation_rate:
            genome, mutation_info = mutate(genome, self.rng, operator_weights=self.operator_weights)
            operator_kind = mutation_info.kind

        child = Individual(
            genome=genome,
            generation=generation,
            parent_ids=[parent_a.genome_hash],
            mutation_history=parent_a.mutation_history + [operator_kind],
        )
        return child, parent_a.genome_hash

    def breed_next_generation(self, generation: int) -> List[Individual]:
        elites = self.pool.elites(self.elite_count)
        next_gen = list(elites)  # carried forward untouched, already scored

        parent_fitness_by_id = {ind.genome_hash: ind.fitness for ind in self.pool.population}
        children_meta = []

        while len(next_gen) < self.population_size:
            child, parent_id = self._breed_child(generation)
            next_gen.append(child)
            children_meta.append({"parent_id": parent_id, "child_ref": child})

        return next_gen, parent_fitness_by_id, children_meta

    # --------------------------------------------------------------- persist

    def persist_generation(self, generation: int):
        gen_dir = self.designs_dir / f"gen_{generation}"
        gen_dir.mkdir(parents=True, exist_ok=True)
        for i, ind in enumerate(self.pool.population):
            (gen_dir / f"individual_{i}_{ind.genome_hash}.v").write_text(ind.genome)

        best = self.pool.best()
        best_dir = self.designs_dir / "best"
        best_dir.mkdir(parents=True, exist_ok=True)
        (best_dir / f"{self.module_name}_best.v").write_text(best.genome)
        (best_dir / f"{self.module_name}_best_report.json").write_text(
            json.dumps(best.fitness_report.as_dict(), indent=2)
        )

        summary = self.pool.summary()
        summary["generation"] = generation
        summary["best_genome_hash"] = best.genome_hash
        summary["timestamp"] = time.time()
        self.history.append(summary)

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps(self.history, indent=2))
        return summary

    # ----------------------------------------------------------------- run

    def run(self):
        self.bootstrap()
        for generation in range(self.generations):
            t0 = time.time()
            self.evaluate_population()
            export_pareto_front_csv(self.pool.population, f"designs/gen_{generation}/pareto_front.csv")
            summary = self.persist_generation(generation)
            elapsed = time.time() - t0
            logger.info(
                "Gen %d | best=%.4f avg=%.4f diversity=%.2f | %.1fs",
                generation, summary["best_fitness"], summary["avg_fitness"],
                summary["diversity"], elapsed,
            )

            if generation == self.generations - 1:
                break  # don't breed a generation we'll never evaluate

            next_gen, parent_fitness_by_id, children_meta = self.breed_next_generation(generation + 1)
            self.pool.replace_generation(next_gen)

            # Score the brand-new children now so reward_backprop has fresh deltas
            self.evaluate_population()
            children = [
                {
                    "parent_id": meta["parent_id"],
                    "operator_kind": meta["child_ref"].mutation_history[-1] if meta["child_ref"].mutation_history else "none",
                    "fitness": meta["child_ref"].fitness,
                }
                for meta in children_meta
            ]
            from reward_backprop import update_credit_from_generation
            self.credit = update_credit_from_generation(self.credit, parent_fitness_by_id, children)
            self.operator_weights = self.credit.as_weights()

        return self.pool.best()
