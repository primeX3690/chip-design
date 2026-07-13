"""
Unit tests for 2_evolutionary_engine/gene_pool.py
Run: pytest tests/unit/test_gene_pool.py -v
"""
import random
from dataclasses import dataclass

from gene_pool import GenePool, Individual


@dataclass
class FakeFitnessReport:
    fitness: float


def make_individual(genome: str, fitness: float, generation: int = 0) -> Individual:
    ind = Individual(genome=genome, generation=generation)
    ind.fitness_report = FakeFitnessReport(fitness=fitness)
    return ind


def test_best_returns_highest_fitness():
    pool = GenePool(rng=random.Random(0))
    pool.add(make_individual("a", 0.3))
    pool.add(make_individual("b", 0.9))
    pool.add(make_individual("c", 0.5))
    assert pool.best().genome == "b"


def test_elites_returns_sorted_top_n():
    pool = GenePool(rng=random.Random(0))
    pool.add(make_individual("a", 0.3))
    pool.add(make_individual("b", 0.9))
    pool.add(make_individual("c", 0.5))
    top2 = pool.elites(2)
    assert [i.genome for i in top2] == ["b", "c"]


def test_tournament_select_prefers_fitter_individuals_statistically():
    pool = GenePool(rng=random.Random(1))
    pool.add(make_individual("weak", 0.01))
    for i in range(5):
        pool.add(make_individual(f"weak{i}", 0.01))
    pool.add(make_individual("strong", 0.99))

    wins = sum(1 for _ in range(200) if pool.tournament_select(k=3).genome == "strong")
    # with 7 individuals and k=3 (sampled without replacement), P(strong in
    # tournament) = C(6,2)/C(7,3) = 15/35 ~= 0.43, and strong always wins
    # when present -> expected ~86 wins in 200 trials. Use a wide but
    # meaningful floor so this isn't flaky while still catching a broken
    # selection function (e.g. one that ignores fitness entirely, which
    # would give ~1/7 ~= 29 wins).
    assert wins > 60


def test_diversity_all_unique():
    pool = GenePool()
    pool.add(make_individual("a", 0.1))
    pool.add(make_individual("b", 0.1))
    pool.add(make_individual("c", 0.1))
    assert pool.diversity() == 1.0


def test_diversity_with_duplicates():
    pool = GenePool()
    pool.add(make_individual("a", 0.1))
    pool.add(make_individual("a", 0.1))
    pool.add(make_individual("b", 0.1))
    assert pool.diversity() == 2 / 3


def test_summary_reports_correct_stats():
    pool = GenePool()
    pool.add(make_individual("a", 0.2))
    pool.add(make_individual("b", 0.8))
    summary = pool.summary()
    assert summary["best_fitness"] == 0.8
    assert summary["worst_fitness"] == 0.2
    assert abs(summary["avg_fitness"] - 0.5) < 1e-9
    assert summary["size"] == 2
