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
from evohdl.sandbox.process_guard import run_guarded  # noqa: E402
from evohdl.paths import SEED_DIR

logger = logging.getLogger("EvoHDL.yosys_synthesizer")

CELL_COUNT_RE = re.compile(r"Number of cells:\s*(\d+)")
# Newer Yosys releases print `stat` as "   1318 cells" instead of "Number of cells: 1318".
CELL_COUNT_RE_NEW = re.compile(r"^\s*(\d+)\s+cells\s*$", re.MULTILINE)
WIRE_COUNT_RE = re.compile(r"Number of wires:\s*(\d+)")
# NOTE: fixed 2026-09 -- the old pattern (`...(\d+)\s*step`) never matched
# real Yosys output ("Longest topological path in <mod> (length=N):"), so
# logic_depth silently came back 0 for every design (alu_basic included).
# Verified against Yosys 0.33 output; kept both patterns for forward/backward
# compatibility across Yosys versions.
LTP_RE = re.compile(r"Longest topological path.*?\(length[=\s]*(\d+)\)", re.IGNORECASE | re.DOTALL)
LTP_RE_LEGACY = re.compile(r"Longest topological path.*?(\d+)\s*step", re.IGNORECASE | re.DOTALL)


def parse_cell_count(output: str):
    """Return the cell count from `stat` output (old or new Yosys format), or None if absent.

    None (not 0) on purpose: a silent 0 once hid a broken `ltp` regex for the whole project.
    """
    m = CELL_COUNT_RE.search(output) or CELL_COUNT_RE_NEW.search(output)
    return int(m.group(1)) if m else None


def yosys_version(yosys_bin: str = "yosys") -> str:
    """Best-effort `yosys -V` string, so reports can say which Yosys produced their numbers."""
    import subprocess
    try:
        r = subprocess.run([yosys_bin, "-V"], capture_output=True, text=True, timeout=10)
        return (r.stdout or r.stderr).strip() or "unknown"
    except Exception:
        return "unknown (yosys not runnable)"


@dataclass
class SynthesisOutcome:
    synthesized: bool
    cell_count: int = 0
    wire_count: int = 0
    logic_depth: int = 0
    log: str = ""
    error: str = ""


def _build_yosys_script(module_name: str, verilog_path: Path, flatten: bool = False, sv: bool = False) -> str:
    sv_flag = " -sv" if sv else ""
    flatten_flag = " -flatten" if flatten else ""
    return f"""
read_verilog{sv_flag} {verilog_path.as_posix()}
hierarchy -check -top {module_name}
proc; opt; fsm; opt; memory; opt
techmap; opt
synth -top {module_name}{flatten_flag}
opt_clean
stat
ltp
"""


def synthesize_design(
    verilog_source: str,
    module_name: str = "alu_basic",
    yosys_bin: str = "yosys",
    timeout_sec: float = 30.0,
    flatten: bool | None = None,
    sv: bool | None = None,
) -> SynthesisOutcome:
    """Synthesize one genome and extract area/delay proxy metrics.

    `flatten` / `sv` default to auto-detection: multi-module sources are flattened (so `stat`
    reports ONE module and the cell count is the whole design), and sources with strong
    SystemVerilog markers are read with `read_verilog -sv`. Single-module Verilog is unchanged.
    """
    from evohdl.sandbox.design_bundle import count_modules, looks_like_systemverilog
    if flatten is None:
        flatten = count_modules(verilog_source) > 1
    if sv is None:
        sv = looks_like_systemverilog(verilog_source)
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_synth_"))
    try:
        design_path = workdir / f"{module_name}.v"
        design_path.write_text(verilog_source)

        script_path = workdir / "run.ys"
        script_path.write_text(_build_yosys_script(module_name, design_path, flatten=flatten, sv=sv))

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
        cells = parse_cell_count(out)
        if cells is None:
            return SynthesisOutcome(
                synthesized=False,
                error="[parse error] could not find a cell count in Yosys `stat` output "
                      "(unsupported Yosys output format?)",
                log=out[-1500:],
            )
        wire_match = WIRE_COUNT_RE.search(out)
        ltp_match = LTP_RE.search(out) or LTP_RE_LEGACY.search(out)
        if not ltp_match:
            logger.warning("No `ltp` logic-depth line found in Yosys output; logic_depth reported as 0.")

        return SynthesisOutcome(
            synthesized=True,
            cell_count=cells,
            wire_count=int(wire_match.group(1)) if wire_match else 0,
            logic_depth=int(ltp_match.group(1)) if ltp_match else 0,
            log=out[-2000:],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    demo_source = SEED_DIR / "alu_basic.v"
    if demo_source.exists():
        outcome = synthesize_design(demo_source.read_text())
        print(outcome)
    else:
        print("Seed design not found for smoke test.")
