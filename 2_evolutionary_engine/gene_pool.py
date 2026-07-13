"""
gene_pool.py
--------------
Population container + selection strategies for the GA.

Keeps each individual's genome, fitness report, generation of birth, and a
content hash (for diversity tracking / duplicate-collapsing). Selection
supports tournament (default, robust to noisy fitness) and roulette
(fitness-proportional).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Optional

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent / "2_evolutionary_engine"))
from fitness_evaluator import FitnessReport  # noqa: E402


@dataclass
class Individual:
    genome: str
    generation: int
    fitness_report: Optional[FitnessReport] = None
    parent_ids: List[str] = field(default_factory=list)
    mutation_history: List[str] = field(default_factory=list)

    @property
    def genome_hash(self) -> str:
        return hashlib.sha1(self.genome.encode("utf-8")).hexdigest()[:10]

    @property
    def fitness(self) -> float:
        return self.fitness_report.fitness if self.fitness_report else 0.0


class GenePool:
    def __init__(self, rng: random.Random | None = None):
        self.population: List[Individual] = []
        self.rng = rng or random.Random()

    # -- population lifecycle -------------------------------------------------

    def seed(self, genome: str, count: int, generation: int = 0):
        self.population = [Individual(genome=genome, generation=generation) for _ in range(count)]

    def add(self, individual: Individual):
        self.population.append(individual)

    def diversity(self) -> float:
        """Fraction of unique genomes in the current population (1.0 = all unique)."""
        if not self.population:
            return 0.0
        unique = len({ind.genome_hash for ind in self.population})
        return unique / len(self.population)

    # -- selection --------------------------------------------------------

    def tournament_select(self, k: int = 3) -> Individual:
        """Pick k random individuals, return the fittest. Robust default selection."""
        contenders = self.rng.sample(self.population, min(k, len(self.population)))
        return max(contenders, key=lambda ind: ind.fitness)

    def roulette_select(self) -> Individual:
        """Fitness-proportional selection. Falls back to uniform if all fitness == 0."""
        total = sum(ind.fitness for ind in self.population)
        if total <= 0:
            return self.rng.choice(self.population)
        pick = self.rng.uniform(0, total)
        running = 0.0
        for ind in self.population:
            running += ind.fitness
            if running >= pick:
                return ind
        return self.population[-1]

    # -- generational replacement ------------------------------------------

    def best(self) -> Individual:
        return max(self.population, key=lambda ind: ind.fitness)

    def elites(self, n: int) -> List[Individual]:
        return sorted(self.population, key=lambda ind: ind.fitness, reverse=True)[:n]

    def replace_generation(self, new_population: List[Individual]):
        self.population = new_population

    def summary(self) -> dict:
        fits = [ind.fitness for ind in self.population]
        return {
            "size": len(self.population),
            "best_fitness": max(fits) if fits else 0.0,
            "avg_fitness": sum(fits) / len(fits) if fits else 0.0,
            "worst_fitness": min(fits) if fits else 0.0,
            "diversity": self.diversity(),
        }
