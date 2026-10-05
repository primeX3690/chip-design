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

import dataclasses
import hashlib
import json
import logging
import random
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import List

from evohdl.paths import REPO_ROOT  # noqa: E402
PROJECT_ROOT = REPO_ROOT
from evohdl.evolutionary_engine.gene_pool import GenePool, Individual  # noqa: E402
from evohdl.evolutionary_engine.verilog_mutator import mutate, configure_resynth  # noqa: E402
from evohdl.evolutionary_engine.crossover_engine import crossover  # noqa: E402
from evohdl.evolutionary_engine.fitness_evaluator import score  # noqa: E402
from evohdl.symbolic_core.design_rule_checker import run_all_checks, analyze_design_support  # noqa: E402
from evohdl.self_improve_loop.design_generator import load_seed_design, generate_initial_population  # noqa: E402
from evohdl.self_improve_loop.reward_backprop import OperatorCredit  # noqa: E402
from evohdl.evolutionary_engine.multi_objective import export_pareto_front_csv
from evohdl.evolutionary_engine.islands import IslandModel, island_sizes  # noqa: E402
from evohdl.sandbox.design_bundle import load_seed_from_config  # noqa: E402
from evohdl.sandbox.testbench_generator import MODULE_RENDERERS  # noqa: E402

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

        # --- 2026-10 additions (all optional; defaults keep the old single-pool behaviour) ---
        # Fitness shaping (gap A/E): "relative_gain" (uncapped, tie==1.0) or "legacy_ratio".
        self.fitness_mode = config.get("fitness_mode", "relative_gain")
        self.area_weight = config.get("area_weight")
        self.delay_weight = config.get("delay_weight")
        # Verification (gap C/G): "simulation" | "formal" | "hybrid" (see fitness_evaluator docstring).
        self.verification_mode = config.get("verification_mode", "simulation")
        self.equiv_timeout = config.get("equiv_timeout_sec", 30.0)
        self.seed_source: str | None = None
        # Island model (gap D): islands == 1 -> exactly the old single population.
        self.n_islands = max(1, int(config.get("islands", 1)))
        self.migration_interval = max(1, int(config.get("migration_interval", 5)))
        self.migration_count = max(1, int(config.get("migration_count", 1)))
        self.migration_topology = config.get("migration_topology", "ring")
        self.island_model: IslandModel | None = (
            IslandModel(self.n_islands, self.rng) if self.n_islands > 1 else None
        )
        # Evaluation cache keyed by full genome hash: duplicates (very common -- elites, no-op
        # mutations, migrants) are never re-verified or re-synthesized.
        self._fitness_cache: dict[str, "FitnessReport"] = {}
        self.cache_hits = 0

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

        bundle = load_seed_from_config(self.config, PROJECT_ROOT)  # one file OR multi-file / hierarchical
        seed_source = bundle.source
        self.seed_source = seed_source
        if bundle.n_modules > 1 or bundle.is_systemverilog:
            logger.info("Seed bundle: top=%s, %d module(s), files=%s, systemverilog=%s "
                        "(multi-module designs are flattened for synthesis/equivalence)",
                        bundle.top, bundle.n_modules, [Path(f).name for f in bundle.files], bundle.is_systemverilog)

        if self.config.get("seed_files"):
            flat = self.designs_dir / "best" / f"{self.module_name}_seed_flat.v"
            flat.parent.mkdir(parents=True, exist_ok=True)
            flat.write_text(seed_source)  # baseline for --full-verify (single concatenated file)

        registered = self.module_name in MODULE_RENDERERS
        if not registered and self.verification_mode in ("simulation", "hybrid"):
            logger.warning("No testbench renderer for '%s' -> switching verification_mode "
                           "%s -> formal (equivalence vs the seed; there is nothing to simulate against).",
                           self.module_name, self.verification_mode)
            self.verification_mode = "formal"

        for msg in analyze_design_support(seed_source, self.module_name, self.verification_mode):
            level = logger.error if msg.startswith("ERROR") else logger.info if msg.startswith("INFO") else logger.warning
            level("Seed support check: %s", msg)
        drc = run_all_checks(seed_source)
        if not drc.passed:
            logger.warning("Seed design has static DRC warnings: %s", drc.violations)

        self._sanity_check_seed(seed_source, registered)

        genomes = generate_initial_population(
            seed_source, self.population_size, diversify_mutations=1, rng=self.rng
        )
        self.pool.seed(genomes[0], 0, generation=0)
        if self.island_model:
            self.island_model.seed_from_genomes(genomes, island_sizes(self.population_size, self.n_islands))
            self._sync_pool()
            logger.info("Island model: %d islands, sizes=%s, migrate %d every %d gen (%s)",
                        self.n_islands, [len(i.population) for i in self.island_model.islands],
                        self.migration_count, self.migration_interval, self.migration_topology)
        else:
            self.pool.population = [Individual(genome=g, generation=0) for g in genomes]
        logger.info("Bootstrapped population of %d from seed design.", len(self.pool.population))

    def _sanity_check_seed(self, seed_source: str, registered: bool) -> None:
        """Formal modes treat the seed as ground truth, so confirm once (if Verilator is available)
        that the seed passes its own testbench. Skipped for unregistered modules / no Verilator."""
        if self.verification_mode == "simulation" or not registered:
            return
        if not shutil.which(self.verilator_bin):
            logger.warning("Verilator not found: cannot sanity-check that the seed passes its testbench; "
                           "formal equivalence will be taken relative to the seed as-is.")
            return
        from evohdl.sandbox.verilator_sandbox import evaluate_design
        sim = evaluate_design(seed_source, module_name=self.module_name,
                              verilator_bin=self.verilator_bin, timeout_sec=self.sim_timeout)
        if not sim.functionally_correct:
            logger.error("SEED FAILS ITS OWN TESTBENCH (%s). Formal equivalence to a wrong seed is "
                         "meaningless -- fix the seed or the golden model first.", sim.error[:200])
        else:
            logger.info("Seed passes its testbench (%d/%d vectors); formal results are anchored to it.",
                        sim.passed, sim.total)

    def _sync_pool(self) -> None:
        """self.pool is the union view of all islands (used for stats/persistence/best)."""
        if self.island_model:
            self.pool.population = self.island_model.all_individuals()

    @staticmethod
    def _full_hash(genome: str) -> str:
        return hashlib.sha1(genome.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------- evaluate

    def _evaluate_one(self, individual: Individual) -> Individual:
        if individual.fitness_report is not None:
            return individual  # already scored (elite carried forward)

        drc = run_all_checks(individual.genome)
        if not drc.passed:
            # Skip the expensive compile step for statically-broken genomes.
            from evohdl.evolutionary_engine.fitness_evaluator import FitnessReport
            individual.fitness_report = FitnessReport(
                fitness=0.0, functionally_correct=False, pass_ratio=0.0,
                cell_count=0, logic_depth=0,
                sim_error=f"DRC failed: {'; '.join(drc.violations)}",
                synth_error="skipped (DRC failed)",
            )
            self._fitness_cache[self._full_hash(individual.genome)] = individual.fitness_report
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
            area_weight=self.area_weight,
            delay_weight=self.delay_weight,
            fitness_mode=self.fitness_mode,
            verification_mode=self.verification_mode,
            seed_source=self.seed_source,
            equiv_timeout=self.equiv_timeout,
        )
        individual.fitness_report = report
        self._fitness_cache[self._full_hash(individual.genome)] = report
        return individual

    def evaluate_population(self):
        unscored = [ind for ind in self.pool.population if ind.fitness_report is None]
        if not unscored:
            return
        # Evaluate each distinct genome once; reuse cached results for everything seen before.
        by_hash: dict[str, list[Individual]] = {}
        for ind in unscored:
            by_hash.setdefault(self._full_hash(ind.genome), []).append(ind)
        to_eval = [group[0] for h, group in by_hash.items() if h not in self._fitness_cache]
        if to_eval:
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {pool.submit(self._evaluate_one, ind): ind for ind in to_eval}
                for future in as_completed(futures):
                    future.result()  # exceptions surface here if any slip through
        saved = 0
        for h, group in by_hash.items():
            report = self._fitness_cache.get(h)
            for ind in group:
                if ind.fitness_report is None and report is not None:
                    ind.fitness_report = dataclasses.replace(report)
                    saved += 1
        self.cache_hits += saved
        if saved:
            logger.debug("Evaluation cache: reused %d result(s) (%d total this run).", saved, self.cache_hits)

    # -------------------------------------------------------------- breed

    def _breed_child(self, generation: int, pool: GenePool | None = None,
                     mutation_rate: float | None = None) -> tuple[Individual, str]:
        pool = pool or self.pool
        mutation_rate = self.mutation_rate if mutation_rate is None else mutation_rate
        parent_a = pool.tournament_select(self.tournament_k)
        genome = parent_a.genome
        operator_kind = "none"

        if self.rng.random() < self.crossover_rate and len(pool.population) > 1:
            parent_b = pool.tournament_select(self.tournament_k)
            genome = crossover(parent_a.genome, parent_b.genome, self.rng).child_source

        if self.rng.random() < mutation_rate:
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

    def _breed_islands(self, generation: int):
        """Each island breeds from ITSELF (own tournament pool, own elites). Mutation pressure varies
        by island (x0.7 .. x1.3) so islands explore at different intensities."""
        parent_fitness_by_id = {ind.genome_hash: ind.fitness for ind in self.pool.population}
        children_meta = []
        n = len(self.island_model)
        for idx, isl in enumerate(self.island_model.islands):
            size = len(isl.population)
            elite_n = min(self.elite_count, max(1, size - 1))
            nxt = list(isl.elites(elite_n))
            rate = min(1.0, self.mutation_rate * (0.7 + 0.6 * idx / max(1, n - 1)))
            while len(nxt) < size:
                child, parent_id = self._breed_child(generation, pool=isl, mutation_rate=rate)
                nxt.append(child)
                children_meta.append({"parent_id": parent_id, "child_ref": child})
            isl.replace_generation(nxt)
        self._sync_pool()
        return parent_fitness_by_id, children_meta

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
        summary["best_area_improvement_pct"] = best.fitness_report.area_improvement_pct
        summary["best_verified_by"] = best.fitness_report.verified_by
        summary["cache_hits"] = self.cache_hits
        if self.island_model:
            summary["island_best_fitness"] = self.island_model.best_per_island()
            summary["migrations_total"] = self.island_model.migrations_done
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

            if self.island_model:
                parent_fitness_by_id, children_meta = self._breed_islands(generation + 1)
            else:
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
            from evohdl.self_improve_loop.reward_backprop import update_credit_from_generation
            self.credit = update_credit_from_generation(self.credit, parent_fitness_by_id, children)
            self.operator_weights = self.credit.as_weights()

            if self.island_model and (generation + 1) % self.migration_interval == 0:
                moved = self.island_model.migrate(self.migration_count, self.migration_topology)
                self._sync_pool()
                logger.info("Gen %d | migration: %d individual(s) exchanged between islands", generation, moved)

        return self.pool.best()
