"""
benchmarks/benchmark_report.py
---------------------------------
Produces the "before vs after" numbers you actually need for a pitch deck
or application: seed design vs. best evolved design, side by side, on
functional correctness, cell count (area), and logic depth (delay).

Usage (after a full run_self_learner.py run has produced designs/best/):

    python benchmarks/benchmark_report.py
    python benchmarks/benchmark_report.py --module alu_basic --out benchmarks/report.md

Requires Verilator + Yosys on PATH (same as the main pipeline).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "2_evolutionary_engine"))
sys.path.append(str(PROJECT_ROOT / "3_sandbox_time"))

from fitness_evaluator import score  # noqa: E402


def format_row(label: str, seed_val, best_val, better: str = "lower") -> str:
    is_bool = isinstance(seed_val, bool) or isinstance(best_val, bool)
    if not is_bool and isinstance(seed_val, (int, float)) and isinstance(best_val, (int, float)) and seed_val:
        pct = (seed_val - best_val) / seed_val * 100
        arrow = f"{pct:+.1f}%"
    else:
        arrow = "n/a"
    return f"| {label} | {seed_val} | {best_val} | {arrow} |"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default="alu_basic")
    parser.add_argument("--seed-design", default=None, help="path override; defaults to designs/seed/<module>.v")
    parser.add_argument("--out", default=None, help="write markdown report to this path in addition to stdout")
    parser.add_argument("--verilator-bin", default="verilator")
    parser.add_argument("--yosys-bin", default="yosys")
    args = parser.parse_args()

    seed_path = Path(args.seed_design) if args.seed_design else PROJECT_ROOT / "designs" / "seed" / f"{args.module}.v"
    best_path = PROJECT_ROOT / "designs" / "best" / f"{args.module}_best.v"

    if not seed_path.exists():
        print(f"ERROR: seed design not found at {seed_path}")
        sys.exit(1)
    if not best_path.exists():
        print(f"ERROR: no evolved design found at {best_path}. Run run_self_learner.py first.")
        sys.exit(1)

    print("Scoring seed design...")
    seed_report = score(seed_path.read_text(), module_name=args.module,
                         verilator_bin=args.verilator_bin, yosys_bin=args.yosys_bin)
    print("Scoring evolved (best) design...")
    best_report = score(best_path.read_text(), module_name=args.module,
                         verilator_bin=args.verilator_bin, yosys_bin=args.yosys_bin)

    lines = [
        f"# EvoHDL Benchmark Report — `{args.module}`",
        "",
        "| Metric | Seed (hand-written) | Evolved (best-of-run) | Change |",
        "|---|---|---|---|",
        format_row("Functionally correct", seed_report.functionally_correct, best_report.functionally_correct),
        format_row("Cell count (area)", seed_report.cell_count, best_report.cell_count),
        format_row("Logic depth (delay proxy)", seed_report.logic_depth, best_report.logic_depth),
        format_row("Fitness score", round(seed_report.fitness, 4), round(best_report.fitness, 4)),
        "",
    ]

    if not best_report.functionally_correct:
        lines.append(
            "**Warning:** the evolved design did not pass functional correctness "
            "in this run. Do not report area/delay improvements from this result "
            "-- re-run with more generations or a larger population."
        )

    report = "\n".join(lines)
    print("\n" + report)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"\nWrote report to {out_path}")


if __name__ == "__main__":
    main()
