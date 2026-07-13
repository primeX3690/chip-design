#!/usr/bin/env python3
"""
utils/report_generator.py
-----------------------------
Turns dashboard/run_history.json into a short markdown summary you can
paste straight into an application or one-pager -- generation count, best
fitness reached, diversity trend, wall-clock time.

Usage:
    python utils/report_generator.py
    python utils/report_generator.py --out RUN_SUMMARY.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = PROJECT_ROOT / "dashboard" / "run_history.json"


def summarize(history: list[dict]) -> str:
    if not history:
        return "No run history found. Run `python run_self_learner.py` first."

    first, last = history[0], history[-1]
    duration_sec = last["timestamp"] - first["timestamp"]
    best_ever = max(h["best_fitness"] for h in history)

    lines = [
        "# EvoHDL Run Summary",
        "",
        f"- Generations completed: **{last['generation'] + 1}**",
        f"- Final population size: **{last['size']}**",
        f"- Best fitness reached: **{best_ever:.4f}**",
        f"- Fitness at generation 0: **{first['best_fitness']:.4f}**",
        f"- Fitness at final generation: **{last['best_fitness']:.4f}**",
        f"- Final population diversity: **{last['diversity']:.2f}**",
        f"- Wall-clock time: **{duration_sec:.1f}s**",
        "",
        "## Generation-by-generation",
        "",
        "| Gen | Best | Avg | Worst | Diversity |",
        "|---|---|---|---|---|",
    ]
    for h in history:
        lines.append(
            f"| {h['generation']} | {h['best_fitness']:.4f} | {h['avg_fitness']:.4f} "
            f"| {h['worst_fitness']:.4f} | {h['diversity']:.2f} |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if not HISTORY_PATH.exists():
        print("No run history found. Run `python run_self_learner.py` first.")
        return

    history = json.loads(HISTORY_PATH.read_text())
    summary = summarize(history)
    print(summary)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(summary)
        print(f"\nWrote summary to {out_path}")


if __name__ == "__main__":
    main()

