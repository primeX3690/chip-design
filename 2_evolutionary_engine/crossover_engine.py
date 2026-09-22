"""
crossover_engine.py
----------------------
Recombines two parent genomes. The "gene" unit is one case-branch of the
ALU's always@(*) block (one opcode's implementation). This is coarser than
real Verilog AST crossover but is safe: swapping whole opcode
implementations between two structurally-identical ALU skeletons can never
produce a syntactically broken module, which keeps compile-failure noise
out of the fitness signal.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

# Generalized from the original alu_basic-only `3'b[01]{3}` pattern so any
# bit-width case-branch selector (e.g. 4'b for picorv32_alu's 10-way ALU
# opcode) is recognized, not just 3-bit opcodes.
BRANCH_RE = re.compile(r"^(\s*)(\d+'b[01]+|default):\s*(.+?);\s*(//.*)?$")


@dataclass
class CrossoverResult:
    child_source: str
    genes_from_parent_a: int
    genes_from_parent_b: int


def _index_branches(source: str) -> Dict[str, int]:
    """Map opcode-literal -> line index, for lines that look like case branches."""
    idx = {}
    for i, line in enumerate(source.splitlines()):
        m = BRANCH_RE.match(line.strip())
        if m:
            idx[m.group(2)] = i
    return idx


def crossover(
    parent_a: str,
    parent_b: str,
    rng: random.Random | None = None,
) -> CrossoverResult:
    """
    Uniform crossover over matching case branches. For each opcode branch
    present in both parents, flip a coin to decide whose implementation the
    child inherits. Falls back to returning parent_a unchanged if the two
    genomes don't share a recognizable branch structure (e.g. one has
    mutated its case statement into something unparseable -- that genome
    will simply lose fitness on its own and get selected out).
    """
    rng = rng or random.Random()

    lines_a = parent_a.splitlines()
    lines_b = parent_b.splitlines()

    branches_a = _index_branches(parent_a)
    branches_b = _index_branches(parent_b)

    shared_opcodes = set(branches_a.keys()) & set(branches_b.keys())
    if not shared_opcodes:
        return CrossoverResult(child_source=parent_a, genes_from_parent_a=1, genes_from_parent_b=0)

    child_lines = list(lines_a)
    from_a, from_b = 0, 0

    for opcode in shared_opcodes:
        if rng.random() < 0.5:
            from_a += 1
            continue  # keep parent_a's line (already in child_lines)
        else:
            child_lines[branches_a[opcode]] = lines_b[branches_b[opcode]]
            from_b += 1

    return CrossoverResult(
        child_source="\n".join(child_lines),
        genes_from_parent_a=from_a,
        genes_from_parent_b=from_b,
    )


def crossover_population_pair(
    pop_pair: Tuple[str, str], rng: random.Random | None = None
) -> List[str]:
    """Produce two children from a pair of parents (child A biased to A, child B biased to B)."""
    rng = rng or random.Random()
    a, b = pop_pair
    child1 = crossover(a, b, rng).child_source
    child2 = crossover(b, a, rng).child_source
    return [child1, child2]


if __name__ == "__main__":
    from pathlib import Path
    seed_path = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    src = seed_path.read_text()
    result = crossover(src, src, random.Random(1))
    print(f"genes_from_a={result.genes_from_parent_a} genes_from_b={result.genes_from_parent_b}")
