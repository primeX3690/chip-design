#!/usr/bin/env python3
"""
utils/verilog_diff.py
------------------------
Prints a unified diff between the seed design and the current best evolved
design. Useful in a live demo: "here's exactly what the algorithm changed."

Usage:
    python utils/verilog_diff.py
    python utils/verilog_diff.py --module alu_basic
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def diff_designs(seed_path: Path, best_path: Path) -> str:
    seed_lines = seed_path.read_text().splitlines(keepends=True)
    best_lines = best_path.read_text().splitlines(keepends=True)
    diff = difflib.unified_diff(
        seed_lines, best_lines,
        fromfile=f"seed/{seed_path.name}",
        tofile=f"best/{best_path.name}",
    )
    return "".join(diff)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default="alu_basic")
    args = parser.parse_args()

    seed_path = PROJECT_ROOT / "designs" / "seed" / f"{args.module}.v"
    best_path = PROJECT_ROOT / "designs" / "best" / f"{args.module}_best.v"

    if not seed_path.exists():
        print(f"ERROR: seed design not found at {seed_path}")
        return
    if not best_path.exists():
        print(f"ERROR: no evolved design yet at {best_path}. Run run_self_learner.py first.")
        return

    diff_text = diff_designs(seed_path, best_path)
    if not diff_text.strip():
        print("No differences -- the evolved design is identical to the seed "
              "(try more generations, or a higher mutation_rate).")
    else:
        print(diff_text)


if __name__ == "__main__":
    main()
