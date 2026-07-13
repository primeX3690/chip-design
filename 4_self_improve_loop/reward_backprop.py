"""
reward_backprop.py
----------------------
"Bias next generation toward what worked" -- a lightweight adaptive
mutation-rate controller. It is not backpropagation in the neural-network
sense; the name reflects its role in the pipeline (feeding fitness deltas
backward into the operator-selection weights the mutator reads next
generation), a common vocabulary in evolutionary-strategy literature.

Mechanism: track a running success score per mutation-operator kind
(operator_swap, constant_tweak, shift_amount, drop_redundant). A mutation
that improved fitness over its parent gets a positive credit; one that
hurt fitness gets a negative credit. Weights are softmax-normalized and
fed into verilog_mutator.mutate(operator_weights=...).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent / "2_evolutionary_engine"))
from verilog_mutator import MUTATION_KIND_NAMES  # noqa: E402

OPERATOR_NAMES = MUTATION_KIND_NAMES


@dataclass
class OperatorCredit:
    scores: Dict[str, float] = field(default_factory=lambda: {name: 0.0 for name in OPERATOR_NAMES})
    counts: Dict[str, int] = field(default_factory=lambda: {name: 0 for name in OPERATOR_NAMES})

    def record(self, operator_name: str, fitness_delta: float):
        if operator_name not in self.scores:
            self.scores[operator_name] = 0.0
            self.counts[operator_name] = 0
        self.scores[operator_name] += fitness_delta
        self.counts[operator_name] += 1

    def average_scores(self) -> Dict[str, float]:
        return {
            name: (self.scores[name] / self.counts[name] if self.counts[name] else 0.0)
            for name in self.scores
        }

    def as_weights(self, temperature: float = 1.0, floor: float = 0.05) -> List[float]:
        """
        Softmax over average per-operator fitness deltas, in the fixed
        MUTATION_OPERATORS order the mutator expects. `floor` guarantees no
        operator ever drops to zero probability -- exploration never fully
        stops, which matters because an operator that looked bad early
        (small population, high variance) may still be useful later.
        """
        avgs = self.average_scores()
        ordered = [avgs.get(name, 0.0) for name in OPERATOR_NAMES]

        max_val = max(ordered) if ordered else 0.0
        exps = [math.exp((v - max_val) / max(temperature, 1e-6)) for v in ordered]
        total = sum(exps) or 1.0
        weights = [e / total for e in exps]

        # apply floor and renormalize
        weights = [max(w, floor) for w in weights]
        total2 = sum(weights)
        weights = [w / total2 for w in weights]
        return weights


def update_credit_from_generation(
    credit: OperatorCredit,
    parent_fitness_by_id: Dict[str, float],
    children: List[dict],
) -> OperatorCredit:
    """
    children: list of dicts with keys {parent_id, operator_kind, fitness}
    produced by evolution_orchestrator during mutation. Computes each
    child's fitness delta vs its immediate parent and records credit.
    """
    for child in children:
        parent_fitness = parent_fitness_by_id.get(child["parent_id"], 0.0)
        delta = child["fitness"] - parent_fitness
        credit.record(child["operator_kind"], delta)
    return credit


if __name__ == "__main__":
    credit = OperatorCredit()
    credit.record("mutate_operator_swap", 0.05)
    credit.record("mutate_constant_tweak", -0.2)
    credit.record("mutate_shift_amount", 0.1)
    print(credit.as_weights())
