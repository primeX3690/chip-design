import random
from evohdl.evolutionary_engine.islands import IslandModel, island_sizes
from evohdl.evolutionary_engine.fitness_evaluator import FitnessReport


def _rep(f):
    return FitnessReport(fitness=f, functionally_correct=True, pass_ratio=1.0, cell_count=1, logic_depth=1,
                         sim_error="", synth_error="")


def _model(n=3, size=5):
    m = IslandModel(n, random.Random(0))
    m.seed_from_genomes([f"g{i}" for i in range(n * size)], island_sizes(n * size, n))
    for k, isl in enumerate(m.islands):
        for j, ind in enumerate(isl.population):
            ind.genome = f"island{k}_ind{j}"
            ind.fitness_report = _rep(k * 10 + j)
    return m


def test_sizes_cover_total_and_respect_minimum():
    assert sum(island_sizes(20, 3)) == 20 and island_sizes(20, 3) == [7, 7, 6]
    assert min(island_sizes(4, 4)) >= 3


def test_every_island_starts_with_the_seed():
    m = IslandModel(3, random.Random(1))
    m.seed_from_genomes(["SEED", "a", "b", "c", "d", "e", "f"], [3, 3, 3])
    assert all(isl.population[0].genome == "SEED" for isl in m.islands)


def test_ring_migration_moves_best_to_next_island_without_evicting_its_best():
    m = _model()
    best_before = [max(i.fitness for i in isl.population) for isl in m.islands]
    moved = m.migrate(count=1, topology="ring")
    assert moved == 3
    for k, isl in enumerate(m.islands):
        prev_best_genome = f"island{(k - 1) % 3}_ind{4}"
        assert any(i.genome == prev_best_genome for i in isl.population)
        assert max(i.fitness for i in isl.population) >= best_before[k]
        assert len(isl.population) == 5


def test_migration_skips_duplicates_and_unscored():
    m = _model(2, 4)
    m.migrate(1)
    assert m.migrate(1) == 0  # same genomes already present -> nothing new to move
    m2 = _model(2, 4)
    for isl in m2.islands:
        for i in isl.population:
            i.fitness_report = None
    assert m2.migrate(1) == 0


def test_single_island_is_a_noop():
    assert _model(1, 5).migrate(2) == 0
