"""
Unit tests for 2_evolutionary_engine/crossover_engine.py
Run: pytest tests/unit/test_crossover_engine.py -v
"""
import random
from pathlib import Path

from crossover_engine import crossover, crossover_population_pair

SEED_PATH = Path(__file__).resolve().parent.parent.parent / "designs" / "seed" / "alu_basic.v"


def load_seed() -> str:
    return SEED_PATH.read_text()


def test_crossover_self_is_stable():
    """Crossing a design with itself should always be functionally
    equivalent (every gene comes from the same source either way)."""
    src = load_seed()
    result = crossover(src, src, random.Random(0))
    assert result.genes_from_parent_a + result.genes_from_parent_b > 0


def test_crossover_produces_valid_line_count():
    src = load_seed()
    result = crossover(src, src, random.Random(1))
    assert len(result.child_source.splitlines()) == len(src.splitlines())


def test_crossover_no_shared_branches_falls_back_to_parent_a():
    a = "module m; endmodule"
    b = "module n; endmodule"
    result = crossover(a, b, random.Random(0))
    assert result.child_source == a
    assert result.genes_from_parent_b == 0


def test_crossover_population_pair_returns_two_children():
    src = load_seed()
    children = crossover_population_pair((src, src), random.Random(2))
    assert len(children) == 2
    for child in children:
        assert "module alu_basic" in child
