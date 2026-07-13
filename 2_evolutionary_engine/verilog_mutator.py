"""
verilog_mutator.py
--------------------
Applies structural mutations to a Verilog genome (string source).

Honesty note: this is a *statement-level* mutator built on regex/line
parsing, not a full Verilog AST transformer. That keeps the system
dependency-light and runnable without a Verilog front-end library. It is
deliberately conservative: mutations only touch the body of the always@(*)
case statement inside the ALU, never the port list, so every mutant stays
instantiable by the fixed testbench (see testbench_generator.py). For a
production-grade successor, swap `_extract_case_body` for a real parser
(e.g. pyverilog / slang) without changing the public mutate() API.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable, List

CASE_LINE_RE = re.compile(r"^(\s*)(3'b[01]{3}|default):\s*(.+?);\s*(//.*)?$")

# Operator swap table: mutating one bitwise/arithmetic op into a
# "neighbouring" one is how the GA explores the design space.
OP_SWAPS = {
    "&": ["|", "^"],
    "|": ["&", "^"],
    "^": ["&", "|"],
    "+": ["-"],
    "-": ["+"],
    "<<": [">>"],
    ">>": ["<<"],
    "~": [""],  # occasionally drop a NOT
}


@dataclass
class Mutation:
    kind: str
    description: str


def _extract_case_lines(source: str) -> List[str]:
    return [ln for ln in source.splitlines() if CASE_LINE_RE.match(ln.strip())]


def mutate_operator_swap(source: str, rng: random.Random) -> tuple[str, Mutation]:
    """Swap one operator on a randomly chosen case-branch RHS."""
    lines = source.splitlines()
    candidate_idxs = [i for i, ln in enumerate(lines) if CASE_LINE_RE.match(ln.strip())]
    if not candidate_idxs:
        return source, Mutation("operator_swap", "no-op: no case branches found")

    idx = rng.choice(candidate_idxs)
    line = lines[idx]

    for op, replacements in OP_SWAPS.items():
        if op in line:
            new_op = rng.choice(replacements)
            # Replace only the first occurrence to keep mutations atomic.
            new_line = line.replace(op, new_op, 1)
            lines[idx] = new_line
            return "\n".join(lines), Mutation(
                "operator_swap", f"line {idx}: '{op}' -> '{new_op or '(removed)'}'"
            )

    return source, Mutation("operator_swap", "no-op: no swappable operator on chosen line")


def mutate_constant_tweak(source: str, rng: random.Random) -> tuple[str, Mutation]:
    """Flip a bit-width literal constant (e.g. 8'b0 -> 8'b1) somewhere in the body."""
    const_re = re.compile(r"(\d+)'b([01]+)")
    matches = list(const_re.finditer(source))
    if not matches:
        return source, Mutation("constant_tweak", "no-op: no bit literals found")

    m = rng.choice(matches)
    width, bits = m.group(1), list(m.group(2))
    bit_idx = rng.randrange(len(bits))
    bits[bit_idx] = "1" if bits[bit_idx] == "0" else "0"
    new_literal = f"{width}'b{''.join(bits)}"
    new_source = source[: m.start()] + new_literal + source[m.end():]
    return new_source, Mutation("constant_tweak", f"flipped bit {bit_idx} of literal at offset {m.start()}")

def mutate_shift_amount(source: str, rng: random.Random) -> tuple[str, Mutation]:
    """Change a shift amount (a << 1 -> a << 2, etc.) within a bounded, safe range."""
    shift_re = re.compile(r"(<<|>>)\s*(\d+)")
    matches = list(shift_re.finditer(source))
    if not matches:
        return source, Mutation("shift_amount", "no-op: no shift ops found")

    m = rng.choice(matches)
    op = m.group(1)
    old_amt = int(m.group(2))
    new_amt = max(1, min(7, old_amt + rng.choice([-1, 1])))
    new_source = source[: m.start()] + f"{op} {new_amt}" + source[m.end():]
    return new_source, Mutation("shift_amount", f"{op} {old_amt} -> {op} {new_amt}")


def mutate_drop_redundant_default(source: str, rng: random.Random) -> tuple[str, Mutation]:
    """Occasionally remove the carry_out reset line to test whether it is redundant
    (this is intentionally allowed to fail fitness -- exploring 'is this logic
    necessary' is exactly what should get selected against if it breaks correctness)."""
    lines = source.splitlines()
    reset_idxs = [i for i, ln in enumerate(lines) if "carry_out = 1'b0" in ln]
    if not reset_idxs:
        return source, Mutation("drop_redundant", "no-op: nothing eligible to drop")
    idx = rng.choice(reset_idxs)
    removed = lines.pop(idx)
    return "\n".join(lines), Mutation("drop_redundant", f"removed line: {removed.strip()}")


MUTATION_OPERATORS: List[Callable[[str, random.Random], tuple[str, Mutation]]] = [
    mutate_operator_swap,
    mutate_constant_tweak,
    mutate_shift_amount,
    mutate_drop_redundant_default,
]

# Short "kind" names as they actually appear in Mutation.kind / mutation_history,
# in the SAME order as MUTATION_OPERATORS. reward_backprop.py keys its credit
# dict off these (not off the Python function __name__, which differs from
# the kind string each function reports -- e.g. mutate_operator_swap()
# reports kind="operator_swap").
MUTATION_KIND_NAMES: List[str] = [
    "operator_swap",
    "constant_tweak",
    "shift_amount",
    "drop_redundant",
]


def mutate(
    source: str,
    rng: random.Random | None = None,
    operator_weights: List[float] | None = None,
) -> tuple[str, Mutation]:
    """
    Apply exactly one mutation operator, chosen either uniformly or per
    `operator_weights` (same order as MUTATION_OPERATORS; see
    reward_backprop.py which adapts these weights generation over generation).
    """
    rng = rng or random.Random()
    if operator_weights and len(operator_weights) == len(MUTATION_OPERATORS):
        op = rng.choices(MUTATION_OPERATORS, weights=operator_weights, k=1)[0]
    else:
        op = rng.choice(MUTATION_OPERATORS)
    return op(source, rng)


if __name__ == "__main__":
    from pathlib import Path
    seed = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    src = seed.read_text()
    mutated, info = mutate(src, random.Random(1))
    print(f"Applied: {info.kind} -> {info.description}")
