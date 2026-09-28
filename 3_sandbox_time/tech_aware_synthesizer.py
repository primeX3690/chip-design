"""
tech_aware_synthesizer.py
--------------------------
Stage-5 addition (2026-09): synthesize a design mapped to a REAL standard-
cell library (e.g. sky130_fd_sc_hd) and read its real area in um^2 directly
from Yosys's `stat -liberty`, WITHOUT needing Docker or the full OpenLane
flow. Only a plain-text `.lib` (Liberty) file is required.

WHY THIS MATTERS (read before wiring this in)
`yosys_synthesizer.py`'s generic `synth` proxy already applies Yosys's own
mature, aggressive technology-independent optimizer (resource sharing,
dead-code elimination, etc.) before reporting cell count. A GA trying to
beat THAT number with RTL-level source mutations is trying to out-optimize
a mature EDA optimizer on its own metric -- a genuinely hard, often near-
saturated target for a small, already-clean seed design (see
benchmarks/*.md: repeated 0% improvement even after fixing the baseline-
wiring bug is consistent with this, not just "too few generations").

Real standard-cell area is a DIFFERENT, better target: two RTL variants can
have identical generic gate-counts yet map to meaningfully different real
areas on an actual library, because real cells have different costs (a
2-input NAND is not the same silicon cost as a 2-input XOR, a MUX cell, or
a full adder cell) that the generic technology-independent proxy is blind
to. Optimizing THIS is closer to what Synopsys/Cadence-style tools actually
target, and is a genuine differentiator worth pitching -- "we optimize
against real standard-cell cost, not a generic gate-count proxy."

HOW TO GET A REAL .lib FILE (no Docker needed for just this)
    pip install volare
    volare enable $(volare list --remote --limit 1) --pdk sky130
    # or manually download sky130_fd_sc_hd__*.lib from the open
    # skywater-pdk / open_pdks project and pass its path directly.
Point `liberty_path` at any sky130_fd_sc_hd__<corner>.lib file it produces
(e.g. .../sky130_fd_sc_hd__tt_025C_1v80.lib for the typical corner).
"""

from __future__ import annotations

import re
import shutil
import tempfile
import logging
from dataclasses import dataclass
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from process_guard import run_guarded  # noqa: E402

logger = logging.getLogger("EvoHDL.tech_aware_synthesizer")

# Yosys's `stat -liberty <file>` prints, among the usual cell breakdown:
#   Chip area for module '\picorv32_alu': 1234.567800
CHIP_AREA_RE = re.compile(r"Chip area for module[^:]*:\s*([\d.]+)")
CELL_COUNT_RE = re.compile(r"Number of cells:\s*(\d+)")


@dataclass
class TechSynthOutcome:
    synthesized: bool
    real_area_um2: float = 0.0
    cell_count: int = 0
    liberty_path: str = ""
    log: str = ""
    error: str = ""


def _build_yosys_script(module_name: str, verilog_path: Path, liberty_path: Path) -> str:
    return f"""
read_verilog {verilog_path.as_posix()}
hierarchy -check -top {module_name}
proc; opt; fsm; opt; memory; opt
techmap; opt
synth -top {module_name}
dfflibmap -liberty {liberty_path.as_posix()}
abc -liberty {liberty_path.as_posix()}
opt_clean
stat -liberty {liberty_path.as_posix()}
"""


def liberty_available(liberty_path: str | None) -> bool:
    """Cheap, no-subprocess check so callers can skip this stage entirely
    (falling back to the generic proxy) when no .lib has been configured --
    this feature is opt-in, never required."""
    return bool(liberty_path) and Path(liberty_path).expanduser().is_file()


def synthesize_tech_mapped(
    verilog_source: str,
    module_name: str,
    liberty_path: str,
    yosys_bin: str = "yosys",
    timeout_sec: float = 60.0,
) -> TechSynthOutcome:
    """Real-standard-cell-mapped synthesis. Needs `abc` bundled with the
    system Yosys install (true for essentially every distro/apt package --
    same binary the generic proxy's `synth` already calls internally for
    its own default technology mapping, just pointed at a real .lib here
    instead of Yosys's built-in generic cell set)."""
    lib_path = Path(liberty_path).expanduser()
    if not lib_path.is_file():
        return TechSynthOutcome(synthesized=False, error=f"liberty file not found: {liberty_path}")

    workdir = Path(tempfile.mkdtemp(prefix="evohdl_techsynth_"))
    try:
        design_path = workdir / f"{module_name}.v"
        design_path.write_text(verilog_source)

        script_path = workdir / "run.ys"
        script_path.write_text(_build_yosys_script(module_name, design_path, lib_path))

        result = run_guarded(
            [yosys_bin, "-Q", "-T", "-s", str(script_path)],
            timeout_sec=timeout_sec,
            cwd=str(workdir),
        )

        if not result.ok:
            reason = "timeout" if result.timed_out else "synthesis error"
            return TechSynthOutcome(
                synthesized=False,
                liberty_path=str(lib_path),
                error=f"[{reason}] {result.stderr[-1500:] or result.stdout[-1500:]}",
                log=result.stdout[-1500:],
            )

        out = result.stdout
        area_match = CHIP_AREA_RE.search(out)
        cell_match = CELL_COUNT_RE.search(out)

        if not area_match:
            # Never silently report 0.0 as if it were a real measurement --
            # that would look like a suspiciously perfect design instead of
            # a parsing failure.
            return TechSynthOutcome(
                synthesized=False,
                liberty_path=str(lib_path),
                error="Yosys ran but no 'Chip area for module' line was found in its output "
                      "(unexpected Yosys version output format, or `abc -liberty` failed silently).",
                log=out[-2000:],
            )

        return TechSynthOutcome(
            synthesized=True,
            real_area_um2=float(area_match.group(1)),
            cell_count=int(cell_match.group(1)) if cell_match else 0,
            liberty_path=str(lib_path),
            log=out[-2000:],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Smoke-test real-library-mapped synthesis on a seed design.")
    parser.add_argument("--verilog", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--liberty", required=True)
    args = parser.parse_args()

    src = Path(args.verilog).read_text()
    outcome = synthesize_tech_mapped(src, args.module, args.liberty)
    print(outcome)
