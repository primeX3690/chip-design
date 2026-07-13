"""
design_generator.py
-----------------------
Produces the generation-0 population. Rather than generating random Verilog
from scratch (which would mostly produce syntactically invalid designs and
waste evaluation budget), EvoHDL seeds the population with the hand-written
reference design and diversifies it with a handful of "free" mutations
up front. This gives the GA a running start with guaranteed-valid genomes.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import List

sys.path.append(str(Path(__file__).resolve().parent.parent / "2_evolutionary_engine"))
from verilog_mutator import mutate  # noqa: E402


def load_seed_design(seed_path: str | Path) -> str:
    seed_path = Path(seed_path)
    if not seed_path.exists():
        raise FileNotFoundError(
            f"Seed design not found at {seed_path}. "
            f"EvoHDL needs at least one hand-written valid Verilog module to bootstrap from."
        )
    return seed_path.read_text()


def generate_initial_population(
    seed_source: str,
    population_size: int,
    diversify_mutations: int = 1,
    rng: random.Random | None = None,
) -> List[str]:
    """
    Returns `population_size` genomes: one exact copy of the seed (to
    guarantee at least one known-good baseline survives generation 0), and
    the rest lightly mutated copies for initial diversity.
    """
    rng = rng or random.Random()
    population = [seed_source]

    while len(population) < population_size:
        genome = seed_source
        for _ in range(diversify_mutations):
            genome, _ = mutate(genome, rng)
        population.append(genome)

    return population


if __name__ == "__main__":
    seed_path = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    seed = load_seed_design(seed_path)
    pop = generate_initial_population(seed, population_size=6, rng=random.Random(0))
    print(f"Generated {len(pop)} initial genomes.")
