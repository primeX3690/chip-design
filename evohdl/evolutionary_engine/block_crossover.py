"""
block_crossover.py
Add to: src/evolution/block_crossover.py  (optional — do this LAST, after
multi_objective.py, baseline_compare.py, and counter_4bit.v are working)

Full Verilog AST-level crossover needs a parser (e.g. pyverilog), which is
a heavier dependency than your current zero-framework philosophy. This is
a lighter middle ground: it crosses over at the "always block" / "assign
statement" boundary instead of raw text-line boundary, so children stay
syntactically closer to valid Verilog and converge faster than pure
line-splicing.

Assumes each genome is stored as a plain string of Verilog source.
"""

import re
import random
from typing import List


def split_into_blocks(rtl_source: str) -> List[str]:
    """Splits a Verilog module body into its top-level always/assign/wire
    blocks. Keeps module header and endmodule separate so they're never
    disturbed by crossover."""
    header_match = re.search(r"module\s+\w+\s*\([^;]*\);", rtl_source, re.DOTALL)
    header = header_match.group(0) if header_match else ""
    footer = "endmodule"

    body = rtl_source
    if header:
        body = body.replace(header, "", 1)
    body = body.replace(footer, "", 1)

    # Split on blank lines between statements/blocks — a pragmatic
    # approximation of "block boundary" without a full parser.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    return [header] + blocks + [footer]


def block_crossover(parent_a: str, parent_b: str) -> str:
    """Produces one child by swapping whole blocks between two parents at
    a random cut point. Falls back to parent_a unchanged if block counts
    don't line up (keeps the GA safe rather than producing garbage)."""
    blocks_a = split_into_blocks(parent_a)
    blocks_b = split_into_blocks(parent_b)

    if len(blocks_a) != len(blocks_b) or len(blocks_a) < 3:
        return parent_a  # header/footer + at least 1 body block required

    cut = random.randint(1, len(blocks_a) - 2)  # never cut header/footer
    child_blocks = blocks_a[:cut] + blocks_b[cut:]
    return "\n\n".join(child_blocks)


def block_crossover_pair(parent_a: str, parent_b: str) -> (str, str):
    """Standard two-child crossover — use this to replace your existing
    crossover() call in the main GA loop."""
    child_1 = block_crossover(parent_a, parent_b)
    child_2 = block_crossover(parent_b, parent_a)
    return child_1, child_2