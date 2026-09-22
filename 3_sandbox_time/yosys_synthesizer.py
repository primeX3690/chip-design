"""
yosys_synthesizer.py
----------------------
Runs Yosys synthesis on a candidate Verilog design and extracts:
  - cell count (proxy for area)
  - estimated logic depth (proxy for delay, via `ltp` longest topological path)

Uses the generic `synth` pass (technology-independent) so no external
standard-cell library is required -- keeps the system runnable out of the
box. A real tapeout flow would swap this for `synth_xxx` + a real .lib via
`config/system_config.yaml`.
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

logger = logging.getLogger("EvoHDL.yosys_synthesizer")

CELL_COUNT_RE = re.compile(r"Number of cells:\s*(\d+)")
WIRE_COUNT_RE = re.compile(r"Number of wires:\s*(\d+)")
# NOTE: fixed 2026-09 -- the old pattern (`...(\d+)\s*step`) never matched
# real Yosys output ("Longest topological path in <mod> (length=N):"), so
# logic_depth silently came back 0 for every design (alu_basic included).
# Verified against Yosys 0.33 output; kept both patterns for forward/backward
# compatibility across Yosys versions.
LTP_RE = re.compile(r"Longest topological path.*?\(length[=\s]*(\d+)\)", re.IGNORECASE | re.DOTALL)
LTP_RE_LEGACY = re.compile(r"Longest topological path.*?(\d+)\s*step", re.IGNORECASE | re.DOTALL)


@dataclass
class SynthesisOutcome:
    synthesized: bool
    cell_count: int = 0
    wire_count: int = 0
    logic_depth: int = 0
    log: str = ""
    error: str = ""


def _build_yosys_script(module_name: str, verilog_path: Path) -> str:
    return f"""
read_verilog {verilog_path.as_posix()}
hierarchy -check -top {module_name}
proc; opt; fsm; opt; memory; opt
techmap; opt
synth -top {module_name}
opt_clean
stat
ltp
"""


def synthesize_design(
    verilog_source: str,
    module_name: str = "alu_basic",
    yosys_bin: str = "yosys",
    timeout_sec: float = 30.0,
) -> SynthesisOutcome:
    """Synthesize one genome and extract area/delay proxy metrics."""
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_synth_"))
    try:
        design_path = workdir / f"{module_name}.v"
        design_path.write_text(verilog_source)

        script_path = workdir / "run.ys"
        script_path.write_text(_build_yosys_script(module_name, design_path))

        result = run_guarded(
            [yosys_bin, "-Q", "-T", "-s", str(script_path)],
            timeout_sec=timeout_sec,
            cwd=str(workdir),
        )

        if not result.ok:
            reason = "timeout" if result.timed_out else "synthesis error"
            return SynthesisOutcome(
                synthesized=False,
                error=f"[{reason}] {result.stderr[-1500:] or result.stdout[-1500:]}",
                log=result.stdout[-1500:],
            )

        out = result.stdout
        cell_match = CELL_COUNT_RE.search(out)
        wire_match = WIRE_COUNT_RE.search(out)
        ltp_match = LTP_RE.search(out) or LTP_RE_LEGACY.search(out)

        return SynthesisOutcome(
            synthesized=True,
            cell_count=int(cell_match.group(1)) if cell_match else 0,
            wire_count=int(wire_match.group(1)) if wire_match else 0,
            logic_depth=int(ltp_match.group(1)) if ltp_match else 0,
            log=out[-2000:],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    demo_source = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    if demo_source.exists():
        outcome = synthesize_design(demo_source.read_text())
        print(outcome)
    else:
        print("Seed design not found for smoke test.")
