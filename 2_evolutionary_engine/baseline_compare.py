"""
baseline_compare.py
---------------------
Point 2 of the "make EvoHDL investor-real" upgrade: turn the GA's raw
fitness score into the headline number a pitch deck actually needs --
measured % area/timing improvement of the evolved design over a real,
human-written baseline.

What counts as the "real human-optimized reference design" here (per the
project brief -- benchmark against a real reference, not a synthetic
strawman): for picorv32_alu, the seed design IS that reference. It is not
a toy -- it's a verbatim-logic extraction of the real, production
PicoRV32 ALU datapath (see designs/seed/picorv32_alu.v header), written by
an experienced HDL engineer and shipped in a core that has been fabricated
on real silicon multiple times. So "baseline vs evolved" here directly
answers "did the GA beat a real expert's shipped RTL", which is the actual
question a reviewer will ask -- not "did it beat a strawman I could have
beaten by hand in five minutes."

This module was broken in three ways before this pass (found while wiring
it up for real, fixed here):
  1. It was never called from anywhere -- run_self_learner.py's flow ended
     at persist_generation() and never invoked compare_to_baseline().
  2. Its `ltp` regex duplicated yosys_synthesizer.py's now-fixed bug (see
     that file's changelog comment) -- reused LTP_RE from there instead of
     re-implementing it a second time.
  3. It hardcoded `["yosys", "-p", script]` instead of taking a
     configurable yosys_bin, so it silently failed to find `yosys` on
     machines where run_self_learner.py's `yosys_bin` config points
     somewhere else (e.g. a WSL2 path).

Usage:
    python 2_evolutionary_engine/baseline_compare.py \
        --module picorv32_alu \
        --baseline designs/seed/picorv32_alu.v \
        --evolved designs/best/picorv32_alu_best.v

or import compare_to_baseline() from hardware_verification_pipeline.py to
fold this into the full real-hardware report.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "3_sandbox_time"))

from yosys_synthesizer import LTP_RE, LTP_RE_LEGACY  # noqa: E402 -- reuse the one fixed regex, don't duplicate it


@dataclass
class SynthStats:
    cell_count: float
    logic_depth: float
    raw_output: str = ""


def run_yosys_stats(verilog_path: str, top_module: str, yosys_bin: str = "yosys") -> SynthStats:
    """Runs the same generic `synth; stat; ltp` Yosys pass yosys_synthesizer.py
    uses for GA fitness, on a single named file -- used here for a clean
    before/after comparison outside the per-generation fitness loop."""
    script = (
        f"read_verilog {verilog_path}; "
        f"hierarchy -check -top {top_module}; "
        f"proc; opt; fsm; opt; memory; opt; "
        f"techmap; opt; "
        f"synth -top {top_module}; "
        f"opt_clean; "
        f"stat; "
        f"ltp"
    )
    result = subprocess.run(
        [yosys_bin, "-Q", "-p", script],
        capture_output=True, text=True, check=True,
    )
    output = result.stdout

    cell_match = re.search(r"Number of cells:\s+(\d+)", output)
    cell_count = float(cell_match.group(1)) if cell_match else float("nan")

    ltp_match = LTP_RE.search(output) or LTP_RE_LEGACY.search(output)
    logic_depth = float(ltp_match.group(1)) if ltp_match else float("nan")

    return SynthStats(cell_count=cell_count, logic_depth=logic_depth, raw_output=output)


def percent_improvement(baseline: SynthStats, evolved: SynthStats) -> dict:
    """Positive % = improvement (reduction). Guards against div-by-zero and
    NaN inputs (e.g. a design with zero logic depth) instead of raising."""
    def pct(base_val, new_val):
        if not base_val or base_val != base_val:  # zero or NaN
            return None
        return round((base_val - new_val) / base_val * 100, 2)

    return {
        "baseline_cell_count": baseline.cell_count,
        "evolved_cell_count": evolved.cell_count,
        "cell_count_improvement_pct": pct(baseline.cell_count, evolved.cell_count),
        "baseline_logic_depth": baseline.logic_depth,
        "evolved_logic_depth": evolved.logic_depth,
        "logic_depth_improvement_pct": pct(baseline.logic_depth, evolved.logic_depth),
    }


def compare_to_baseline(
    baseline_rtl_path: str,
    evolved_rtl_path: str,
    top_module: str,
    yosys_bin: str = "yosys",
) -> dict:
    """Main entry point -- call once at the end of a run, after the GA has
    written out its best individual's RTL to disk."""
    baseline_stats = run_yosys_stats(baseline_rtl_path, top_module, yosys_bin)
    evolved_stats = run_yosys_stats(evolved_rtl_path, top_module, yosys_bin)
    result = percent_improvement(baseline_stats, evolved_stats)
    result["module_name"] = top_module
    result["baseline_rtl_path"] = baseline_rtl_path
    result["evolved_rtl_path"] = evolved_rtl_path
    return result


def render_markdown_report(result: dict) -> str:
    cell_pct = result["cell_count_improvement_pct"]
    depth_pct = result["logic_depth_improvement_pct"]
    cell_line = f"{cell_pct:+.1f}%" if cell_pct is not None else "n/a"
    depth_line = f"{depth_pct:+.1f}%" if depth_pct is not None else "n/a"

    return f"""# EvoHDL Baseline vs Evolved -- {result['module_name']}

Baseline (human-written reference): `{result['baseline_rtl_path']}`
Evolved (GA best individual): `{result['evolved_rtl_path']}`

| Metric | Baseline | Evolved | Improvement |
|---|---|---|---|
| Cell count (generic synth) | {result['baseline_cell_count']:.0f} | {result['evolved_cell_count']:.0f} | {cell_line} |
| Logic depth (levels, Yosys `ltp`) | {result['baseline_logic_depth']:.0f} | {result['evolved_logic_depth']:.0f} | {depth_line} |

Cell count and logic depth are technology-independent Yosys `synth` proxies
(fast, used as the GA's per-generation fitness signal). For real,
silicon-referenced numbers (um^2 die area on SkyWater 130nm, picosecond
timing, routed FPGA congestion), see `benchmarks/hardware_verification_report.md`,
produced by `hardware_verification_pipeline.py` via OpenLane + OpenSTA +
nextpnr.
"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compare a baseline vs GA-evolved RTL design")
    parser.add_argument("--module", default="picorv32_alu")
    parser.add_argument("--baseline", default="designs/seed/picorv32_alu.v")
    parser.add_argument("--evolved", default="designs/best/picorv32_alu_best.v")
    parser.add_argument("--yosys-bin", default="yosys")
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)
    args = parser.parse_args()

    result = compare_to_baseline(args.baseline, args.evolved, args.module, args.yosys_bin)
    print(json.dumps(result, indent=2))

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(result, indent=2))
    if args.out_md:
        Path(args.out_md).write_text(render_markdown_report(result))
