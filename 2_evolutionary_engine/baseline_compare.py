"""
baseline_compare.py
Add to: src/evaluation/baseline_compare.py  (next to your yosys_wrapper.py /
verilator_wrapper.py)

Runs Yosys synthesis stats on the ORIGINAL unoptimized RTL (the seed
individual, before evolution) and on your BEST evolved individual, then
computes the % improvement — this is the headline number for the
fellowship writeup instead of a raw fitness score.
"""

import re
import subprocess
from dataclasses import dataclass


@dataclass
class SynthStats:
    area: float      # cell count / um^2 depending on your Yosys flow
    timing: float     # critical path delay, ns


def run_yosys_stats(verilog_path: str, top_module: str) -> SynthStats:
    """Runs `yosys -p "synth; stat"` on a Verilog file and parses area/timing.
    Adjust the yosys script string here if your existing yosys_wrapper.py
    already builds a synth script — reuse that instead of duplicating it."""
    script = (
        f"read_verilog {verilog_path}; "
        f"synth -top {top_module}; "
        f"stat; "
        f"ltp"
    )
    result = subprocess.run(
        ["yosys", "-p", script],
        capture_output=True, text=True, check=True
    )
    output = result.stdout

    # Adjust these regexes to match your actual Yosys report format —
    # this matches the standard "Number of cells" / timing report lines.
    cell_match = re.search(r"Number of cells:\s+(\d+)", output)
    area = float(cell_match.group(1)) if cell_match else float("nan")

    timing_match = re.search(r"length\s*=\s*(\d+)", output)
    timing = float(timing_match.group(1)) if timing_match else float("nan")

    return SynthStats(area=area, timing=timing)


def percent_improvement(baseline: SynthStats, evolved: SynthStats) -> dict:
    """Positive % = improvement (reduction), negative % = evolved got worse."""
    area_improvement = (baseline.area - evolved.area) / baseline.area * 100
    timing_improvement = (baseline.timing - evolved.timing) / baseline.timing * 100
    return {
        "baseline_area": baseline.area,
        "evolved_area": evolved.area,
        "area_improvement_pct": round(area_improvement, 2),
        "baseline_timing": baseline.timing,
        "evolved_timing": evolved.timing,
        "timing_improvement_pct": round(timing_improvement, 2),
    }


def compare_to_baseline(baseline_rtl_path: str, evolved_rtl_path: str, top_module: str) -> dict:
    """Main entry point — call once at the end of a run, after your GA
    has written out its best individual's RTL to a file."""
    baseline_stats = run_yosys_stats(baseline_rtl_path, top_module)
    evolved_stats = run_yosys_stats(evolved_rtl_path, top_module)
    return percent_improvement(baseline_stats, evolved_stats)


if __name__ == "__main__":
    # Example usage — replace paths with your actual seed RTL and best
    # evolved individual once a run finishes.
    result = compare_to_baseline(
    baseline_rtl_path="designs/seed/alu_basic.v",
    evolved_rtl_path="designs/best/alu_basic_best.v",
    top_module="alu_basic",
)
    
    print(result)