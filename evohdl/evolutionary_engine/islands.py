"""
islands.py
-----------
Island-model GA (gap D): the population is split into independent sub-populations that evolve
separately and periodically exchange their best individuals (migration). Isolation keeps
different islands in different basins of the search space; migration spreads good building
blocks without letting one lineage take over everywhere (premature convergence).

Migrants are COPIES that keep their already-computed fitness report, so migration costs no
re-evaluation. Each island's worst individuals are replaced; an island's own best is never evicted.
"""
from __future__ import annotations

import dataclasses
import random
from typing import List, Sequence

from evohdl.evolutionary_engine.gene_pool import GenePool, Individual


def island_sizes(total: int, n_islands: int, min_size: int = 3) -> List[int]:
    """Split `total` individuals over islands as evenly as possible (each at least `min_size`)."""
    n_islands = max(1, n_islands)
    base, extra = divmod(total, n_islands)
    sizes = [max(min_size, base + (1 if i < extra else 0)) for i in range(n_islands)]
    return sizes


class IslandModel:
    def __init__(self, n_islands: int, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.islands: List[GenePool] = [GenePool(rng=self.rng) for _ in range(max(1, n_islands))]
        self.migrations_done = 0

    def __len__(self) -> int:
        return len(self.islands)

    def seed_from_genomes(self, genomes: Sequence[str], sizes: Sequence[int], generation: int = 0) -> None:
        """Island i gets sizes[i] genomes. Every island starts with an exact copy of genomes[0] (the seed),
        so each island holds a known-correct baseline."""
        seed = genomes[0]
        pool = list(genomes[1:])
        for isl, size in zip(self.islands, sizes):
            members = [seed]
            while len(members) < size:
                members.append(pool.pop(0) if pool else seed)
            isl.population = [Individual(genome=g, generation=generation) for g in members]

    def all_individuals(self) -> List[Individual]:
        return [ind for isl in self.islands for ind in isl.population]

    def best_per_island(self) -> List[float]:
        return [max((i.fitness for i in isl.population), default=0.0) for isl in self.islands]

    def migrate(self, count: int = 1, topology: str = "ring") -> int:
        """Move copies of each island's top `count` (scored) individuals to a destination island.

        topology: "ring" (i -> i+1) or "random" (i -> a random other island).
        Returns the number of individuals actually transferred (duplicates are skipped).
        """
        n = len(self.islands)
        if n < 2:
            return 0
        emigrants = [[e for e in isl.elites(count) if e.fitness_report is not None] for isl in self.islands]
        moved = 0
        for i, batch in enumerate(emigrants):
            dest_idx = (i + 1) % n if topology != "random" else self.rng.choice([j for j in range(n) if j != i])
            dest = self.islands[dest_idx]
            have = {ind.genome_hash for ind in dest.population}
            fresh = [e for e in batch if e.genome_hash not in have]
            # never replace more than half an island, and never its current best
            fresh = fresh[: max(0, len(dest.population) // 2)]
            if not fresh:
                continue
            order = sorted(range(len(dest.population)), key=lambda k: dest.population[k].fitness)
            for slot, e in zip(order, fresh):
                dest.population[slot] = dataclasses.replace(
                    e, parent_ids=e.parent_ids + [e.genome_hash],
                    mutation_history=e.mutation_history + ["migrated"],
                )
                moved += 1
        self.migrations_done += moved
        return moved
