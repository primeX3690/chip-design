"""
opensta_runner.py
--------------------
Point 4 of the "make EvoHDL investor-real" upgrade: run the real OpenSTA
static timing analyzer against a synthesized gate-level netlist + the real
SkyWater sky130_fd_sc_hd liberty (.lib) timing model, and parse out an
actual picosecond-level delay number -- not Yosys's `ltp` logic-level count.

Typical pipeline this plugs into (see hardware_verification_pipeline.py):
  1. yosys_synthesizer.py (fast, generic `synth`)   -- used every generation
     by the GA for speed; produces cell-count / logic-depth PROXIES.
  2. openlane_runner.py (real sky130 P&R)           -- run once, on the
     best genome; produces the real gate-level netlist AND real die area.
  3. opensta_runner.py (this file)                  -- run once, on that
     same netlist, against the real sky130 timing library, to report the
     real worst-case path delay in picoseconds.

Requirements (see README.md "Real Hardware Verification Flow"):
  - OpenSTA built/installed and on PATH as `sta`
    (https://github.com/parallaxsw/OpenSTA -- not packaged for apt/pip;
    build from source or use the `opensta/opensta` Docker image)
  - A sky130_fd_sc_hd liberty file (ships inside the sky130A PDK that
    OpenLane/volare already downloads -- reuse that same PDK_ROOT instead
    of downloading it twice)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("EvoHDL.opensta_runner")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STA_SCRIPT = PROJECT_ROOT / "flow" / "opensta" / "run_sta.tcl"

WNS_RE = re.compile(r"wns\s+(-?\d+\.?\d*)", re.IGNORECASE)
TNS_RE = re.compile(r"tns\s+(-?\d+\.?\d*)", re.IGNORECASE)
# "data arrival time <ps>" is OpenSTA's own report_checks line for the
# critical path's total delay.
ARRIVAL_RE = re.compile(r"data arrival time\s+(-?\d+\.?\d*)", re.IGNORECASE)


@dataclass
class STAOutcome:
    ran: bool
    worst_negative_slack_ps: Optional[float] = None
    total_negative_slack_ps: Optional[float] = None
    critical_path_delay_ps: Optional[float] = None
    raw_report: str = ""
    error: str = ""


def opensta_available() -> bool:
    return shutil.which("sta") is not None


def find_sky130_liberty(pdk_root: str | Path = "~/.volare",
                         corner: str = "tt_025C_1v80") -> Optional[Path]:
    """
    Locate the sky130_fd_sc_hd liberty file for a given PVT corner inside a
    volare/OpenLane-managed PDK root, so callers don't need to hardcode the
    exact nested path (which includes a PDK version hash directory).
    """
    pdk_root = Path(pdk_root).expanduser()
    if not pdk_root.exists():
        return None
    pattern = f"sky130_fd_sc_hd__{corner}.lib"
    matches = list(pdk_root.rglob(pattern))
    return matches[0] if matches else None


def run_sta(
    netlist_path: str | Path,
    top_module: str,
    liberty_path: str | Path,
    clock_port: Optional[str] = None,
    clock_period_ns: float = 10.0,
    sta_bin: str = "sta",
    timeout_sec: float = 300.0,
) -> STAOutcome:
    """
    Runs flow/opensta/run_sta.tcl through the real `sta` binary and parses
    the actual reported slack/delay numbers, in picoseconds.
    """
    if not shutil.which(sta_bin):
        return STAOutcome(ran=False, error=f"OpenSTA binary '{sta_bin}' not found on PATH")

    netlist_path = Path(netlist_path)
    liberty_path = Path(liberty_path)
    if not netlist_path.exists():
        return STAOutcome(ran=False, error=f"netlist not found: {netlist_path}")
    if not liberty_path.exists():
        return STAOutcome(ran=False, error=f"liberty file not found: {liberty_path}")

    env = os.environ.copy()
    env["LIB_FILE"] = str(liberty_path)
    env["NETLIST_FILE"] = str(netlist_path)
    env["TOP_MODULE"] = top_module
    env["CLOCK_PORT"] = clock_port or ""
    env["CLOCK_PERIOD_NS"] = str(clock_period_ns)

    cmd = [sta_bin, "-no_init", "-exit", str(STA_SCRIPT)]
    logger.info("Running OpenSTA: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return STAOutcome(ran=False, error=f"OpenSTA exceeded {timeout_sec}s timeout")

    out = result.stdout + "\n" + result.stderr
    if result.returncode != 0 and "EVOHDL_STA_BEGIN" not in out:
        return STAOutcome(ran=False, error=f"OpenSTA exited {result.returncode}: {out[-2000:]}", raw_report=out)

    wns_match = WNS_RE.search(out)
    tns_match = TNS_RE.search(out)
    arrival_matches = ARRIVAL_RE.findall(out)

    # report_checks -path_delay max reports the worst (largest) arrival time
    # first; OpenSTA's own units are set to ps by `set_units -time ps` in
    # run_sta.tcl, so no unit conversion is needed here.
    critical_delay_ps = float(arrival_matches[0]) if arrival_matches else None

    return STAOutcome(
        ran=True,
        worst_negative_slack_ps=float(wns_match.group(1)) if wns_match else None,
        total_negative_slack_ps=float(tns_match.group(1)) if tns_match else None,
        critical_path_delay_ps=critical_delay_ps,
        raw_report=out[-4000:],
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run real OpenSTA timing analysis on a synthesized netlist")
    parser.add_argument("netlist_path")
    parser.add_argument("top_module")
    parser.add_argument("--liberty", default=None, help="path to sky130_fd_sc_hd__*.lib (auto-detected under --pdk-root if omitted)")
    parser.add_argument("--pdk-root", default="~/.volare")
    parser.add_argument("--clock-port", default=None)
    parser.add_argument("--clock-period-ns", type=float, default=10.0)
    args = parser.parse_args()

    liberty = Path(args.liberty) if args.liberty else find_sky130_liberty(args.pdk_root)
    if liberty is None:
        print("[SKIP] no sky130 liberty file found -- pass --liberty or install the PDK via volare/OpenLane")
    elif not opensta_available():
        print("[SKIP] OpenSTA ('sta') not found on PATH -- see README.md 'Real Hardware Verification Flow'")
    else:
        outcome = run_sta(args.netlist_path, args.top_module, liberty, args.clock_port, args.clock_period_ns)
        print(outcome)
