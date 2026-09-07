"""
multi_objective.py
Add to: src/evolution/multi_objective.py  (alongside your existing genetic_algorithm.py)

Replaces single-score fitness with NSGA-II-style Pareto ranking on
(area, timing) so you can show a trade-off curve instead of one number.

Assumes each Individual has:
    individual.area    -> float  (lower is better)
    individual.timing  -> float  (lower is better)
If your class uses different attribute names, just rename them below.
"""

from typing import List
from pathlib import Path


class Individual:
    """Minimal stand-in so this file runs standalone. Replace with your real class."""
    def __init__(self, genome, area: float, timing: float):
        self.genome = genome
        self.area = area
        self.timing = timing
        self.rank = None
        self.crowding_distance = 0.0



def dominates(a: Individual, b: Individual) -> bool:
    """True if 'a' Pareto-dominates 'b' (a is at least as good in both
    objectives and strictly better in at least one)."""
    a_area, a_timing = a.fitness_report.cell_count, a.fitness_report.logic_depth
    b_area, b_timing = b.fitness_report.cell_count, b.fitness_report.logic_depth
    not_worse = (a_area <= b_area) and (a_timing <= b_timing)
    strictly_better = (a_area < b_area) or (a_timing < b_timing)
    return not_worse and strictly_better


def fast_non_dominated_sort(population: List[Individual]) -> List[List[Individual]]:
    """Classic NSGA-II sort. Returns fronts[0] = best (rank 0) Pareto front,
    fronts[1] = next front, etc."""
    fronts: List[List[Individual]] = [[]]
    domination_count = {id(p): 0 for p in population}
    dominated_solutions = {id(p): [] for p in population}

    for p in population:
        for q in population:
            if p is q:
                continue
            if dominates(p, q):
                dominated_solutions[id(p)].append(q)
            elif dominates(q, p):
                domination_count[id(p)] += 1
        if domination_count[id(p)] == 0:
            p.rank = 0
            fronts[0].append(p)

    i = 0
    while fronts[i]:
        next_front = []
        for p in fronts[i]:
            for q in dominated_solutions[id(p)]:
                domination_count[id(q)] -= 1
                if domination_count[id(q)] == 0:
                    q.rank = i + 1
                    next_front.append(q)
        i += 1
        fronts.append(next_front)

    fronts.pop()  # last one is always empty
    return fronts


def crowding_distance(front: List[Individual]) -> None:
    """Assigns .crowding_distance in-place; used as the tie-breaker within
    a front so selection favors spread-out solutions along the trade-off curve."""
    if not front:
        return
    n = len(front)
    for ind in front:
        ind.crowding_distance = 0.0


    for attr in ("cell_count", "logic_depth"):
        front.sort(key=lambda ind: getattr(ind.fitness_report, attr))
        front[0].crowding_distance = float("inf")
        front[-1].crowding_distance = float("inf")

        obj_min = getattr(front[0].fitness_report, attr)
        obj_max = getattr(front[-1].fitness_report, attr)
        if obj_max == obj_min:
            continue
        for i in range(1, n - 1):
            prev_val = getattr(front[i - 1].fitness_report, attr)
            next_val = getattr(front[i + 1].fitness_report, attr)
            front[i].crowding_distance += (next_val - prev_val) / (obj_max - obj_min)


def select_next_generation(population: List[Individual], pop_size: int) -> List[Individual]:
    """Drop-in replacement for your current tournament-selection-only step.
    Fills the next generation front-by-front, using crowding distance to
    pick the most diverse individuals from the last partially-included front."""
    fronts = fast_non_dominated_sort(population)
    next_gen: List[Individual] = []

    for front in fronts:
        crowding_distance(front)
        if len(next_gen) + len(front) <= pop_size:
            next_gen.extend(front)
        else:
            remaining = pop_size - len(next_gen)
            front.sort(key=lambda ind: ind.crowding_distance, reverse=True)
            next_gen.extend(front[:remaining])
            break

    return next_gen


def export_pareto_front_csv(population: List[Individual], path: str) -> None:
    """Call this once per generation from your Streamlit dashboard code to
    log the front for the area-vs-timing scatter plot."""
    fronts = fast_non_dominated_sort(population)
    pareto_front = fronts[0]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("area,timing\n")
        for ind in sorted(pareto_front, key=lambda i: i.fitness_report.cell_count):
            f.write(f"{ind.fitness_report.cell_count},{ind.fitness_report.logic_depth}\n")
