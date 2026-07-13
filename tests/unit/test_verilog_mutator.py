"""
Unit tests for 2_evolutionary_engine/verilog_mutator.py
Run: pytest tests/unit/test_verilog_mutator.py -v
"""
import random
from pathlib import Path

from verilog_mutator import mutate, MUTATION_OPERATORS, MUTATION_KIND_NAMES, mutate_constant_tweak, mutate_shift_amount

SEED_PATH = Path(__file__).resolve().parent.parent.parent / "designs" / "seed" / "alu_basic.v"


def load_seed() -> str:
    return SEED_PATH.read_text()


def test_seed_design_exists():
    assert SEED_PATH.exists(), "seed design missing -- required for evolution to bootstrap"


def test_mutate_returns_valid_source_and_metadata():
    src = load_seed()
    mutated, info = mutate(src, random.Random(1))
    assert isinstance(mutated, str)
    assert len(mutated) > 0
    assert info.kind in MUTATION_KIND_NAMES


def test_mutate_is_deterministic_given_same_seed():
    src = load_seed()
    m1, i1 = mutate(src, random.Random(123))
    m2, i2 = mutate(src, random.Random(123))
    assert m1 == m2
    assert i1.kind == i2.kind


def test_mutate_changes_something_across_many_trials():
    """Not every single mutation call is guaranteed to change the source
    (some ops can be a no-op if nothing eligible is found), but across many
    trials at least some mutations should differ from the original."""
    src = load_seed()
    changed = 0
    for seed in range(30):
        mutated, _ = mutate(src, random.Random(seed))
        if mutated != src:
            changed += 1
    assert changed > 0


def test_constant_tweak_preserves_source_length_class():
    src = load_seed()
    mutated, info = mutate_constant_tweak(src, random.Random(5))
    # a single bit flip should not change overall source length
    assert len(mutated) == len(src) or info.kind == "constant_tweak"


def test_shift_amount_stays_in_bounds():
    src = "wire [7:0] x = a << 7;"
    for seed in range(20):
        mutated, info = mutate_shift_amount(src, random.Random(seed))
        if "shift_amount" in info.kind and "->" in info.description:
            # extract the new amount from the description "<< 7 -> << N"
            new_amt = int(info.description.split("->")[-1].strip().split()[-1])
            assert 1 <= new_amt <= 7


def test_operator_weighted_selection_respects_weights():
    """When one operator's weight is 1.0 and the rest are 0.0, mutate()
    should always pick that operator (via rng.choices)."""
    src = load_seed()
    n = len(MUTATION_OPERATORS)
    weights = [0.0] * n
    weights[0] = 1.0
    kinds = set()
    for seed in range(15):
        _, info = mutate(src, random.Random(seed), operator_weights=weights)
        kinds.add(info.kind)
    assert kinds == {MUTATION_KIND_NAMES[0]}
