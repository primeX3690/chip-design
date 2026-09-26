"""
openlane_runner.py
--------------------
Point 3 of the "make EvoHDL investor-real" upgrade: run a genome through the
real OpenLane RTL-to-GDSII flow on the open SkyWater 130nm PDK
(sky130_fd_sc_hd), instead of Yosys's technology-independent `synth` pass.
This gives area in real fabrication units (um^2) and a routed netlist that
opensta_runner.py can then run real static timing analysis on.

Why this is a separate, opt-in stage instead of the per-generation fitness
function: a full OpenLane run (synthesis -> floorplan -> placement ->
CTS -> routing -> DRC/LVS) takes minutes per design, not milliseconds. The
GA still uses the fast generic-Yosys `synth` pass (yosys_synthesizer.py) as
its fitness function across hundreds of individuals x dozens of generations
-- that is what makes the search tractable on a laptop. This module runs
ONCE, at the end, on the single best genome the GA found, to turn the GA's
relative "cells got smaller" signal into an absolute, silicon-referenced
number for a pitch deck: "X um^2, sky130, before vs after".

Requirements (NOT installed by this repo's pip requirements -- these are
multi-GB EDA toolchain containers, see README.md "Real Hardware
Verification Flow"):
  - Docker (or Podman) able to pull ghcr.io/efabless/openlane images
  - The sky130 PDK volume that OpenLane's own installer manages
    (`openlane --pdk-root ~/.volare ...` or the `volare` tool)

This module never blocks the GA loop -- if Docker/OpenLane isn't installed,
run_self_learner.py's normal run still works exactly as before. This is
only invoked by hardware_verification_pipeline.py / --full-verify.
"""

from __future__ import annotations

import csv
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("EvoHDL.openlane_runner")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOW_DIR = PROJECT_ROOT / "flow" / "openlane"


@dataclass
class OpenLaneOutcome:
    ran: bool
    die_area_um2: float = 0.0
    core_area_um2: float = 0.0
    cell_count: int = 0
    worst_setup_slack_ns: Optional[float] = None
    worst_hold_slack_ns: Optional[float] = None
    run_dir: str = ""
    error: str = ""


def openlane_available() -> bool:
    """True if we can plausibly launch the OpenLane docker flow at all."""
    return shutil.which("docker") is not None


def _write_design_config(module_name: str, verilog_path: Path, run_root: Path,
                          clock_port: str | None, clock_period_ns: float) -> Path:
    """Build a per-run OpenLane config.json + design/src/ layout from the
    flow/openlane/config.json template."""
    design_dir = run_root / "designs" / module_name
    src_dir = design_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    (src_dir / f"{module_name}.v").write_text(verilog_path.read_text())

    template = json.loads((FLOW_DIR / "config.json").read_text())
    template["DESIGN_NAME"] = module_name
    template["VERILOG_FILES"] = f"dir::src/{module_name}.v"
    template["CLOCK_PORT"] = clock_port
    template["CLOCK_NET"] = clock_port
    template["CLOCK_PERIOD"] = clock_period_ns
    template.pop("_comment", None)
    template.pop("_clock_note", None)

    config_path = design_dir / "config.json"
    config_path.write_text(json.dumps(template, indent=2))
    return design_dir

def run_openlane(
    verilog_path: str | Path,
    module_name: str,
    clock_port: str | None = None,
    clock_period_ns: float = 10.0,
    pdk_root: str | Path = "~/.volare",
    timeout_sec: float = 3600.0,
    run_root: str | Path | None = None,
) -> OpenLaneOutcome:
    if not openlane_available():
        return OpenLaneOutcome(ran=False, error="docker not found on PATH -- install Docker to run the real sky130 flow")

    verilog_path = Path(verilog_path)
    pdk_root = Path(pdk_root).expanduser()
    run_root = Path(run_root) if run_root else Path.cwd() / "flow" / "openlane" / "_runs" / module_name
    run_root.mkdir(parents=True, exist_ok=True)

    design_dir = _write_design_config(module_name, verilog_path, run_root, clock_port, clock_period_ns)

    cmd = [
        "python3", "-m", "librelane",
        "--dockerized",
        "--pdk-root", str(pdk_root),
        str(design_dir / "config.json"),
    ]

    logger.info("Launching LibreLane (sky130, dockerized): %s", " ".join(cmd))
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except FileNotFoundError:
        return OpenLaneOutcome(ran=False, error="docker executable not found")
    except subprocess.TimeoutExpired:
        return OpenLaneOutcome(ran=False, error=f"OpenLane run exceeded {timeout_sec}s timeout")

    if result.returncode != 0:
        return OpenLaneOutcome(
            ran=False,
            error=f"OpenLane exited {result.returncode}: {result.stderr[-2000:] or result.stdout[-2000:]}",
        )

    return _parse_openlane_run(design_dir, run_root)


def _parse_openlane_run(design_dir: Path, run_root: Path) -> OpenLaneOutcome:
    """
    OpenLane 2.x writes a per-run `runs/<tag>/final/metrics.csv` (and a
    `runs/<tag>/final/final_summary_report.csv` in some versions). Take the
    most recently modified `runs/*` directory and pull the real numbers out
    of whichever metrics file is present, rather than assuming one exact
    OpenLane version's file layout.
    """
    runs_dir = design_dir / "runs"
    if not runs_dir.exists():
        return OpenLaneOutcome(ran=False, error=f"no runs/ directory produced under {design_dir}", run_dir=str(design_dir))

    run_dirs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not run_dirs:
        return OpenLaneOutcome(ran=False, error="runs/ directory is empty", run_dir=str(design_dir))
    latest_run = run_dirs[0]

    metrics_candidates = list(latest_run.glob("final/metrics.csv")) + list(latest_run.glob("*/metrics.csv"))
    if not metrics_candidates:
        return OpenLaneOutcome(ran=False, error="no metrics.csv found in OpenLane run output", run_dir=str(latest_run))

    metrics: dict[str, str] = {}
    with open(metrics_candidates[0]) as f:
        reader = csv.reader(f)
        rows = list(reader)
        if len(rows) >= 2:
            metrics = dict(zip(rows[0], rows[1]))

    def _num(key: str, default: float = 0.0) -> float:
        try:
            return float(metrics.get(key, default))
        except (TypeError, ValueError):
            return default

    return OpenLaneOutcome(
        ran=True,
        die_area_um2=_num("design__die__area"),
        core_area_um2=_num("design__core__area", _num("design__die__area")),
        cell_count=int(_num("design__instance__count")),
        worst_setup_slack_ns=metrics.get("timing__setup__ws"),
        worst_hold_slack_ns=metrics.get("timing__hold__ws"),
        run_dir=str(latest_run),
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run one Verilog design through the real OpenLane/sky130 flow")
    parser.add_argument("verilog_path")
    parser.add_argument("module_name")
    parser.add_argument("--clock-port", default=None)
    parser.add_argument("--clock-period-ns", type=float, default=10.0)
    args = parser.parse_args()

    if not openlane_available():
        print("[SKIP] docker not found on PATH -- see README.md 'Real Hardware Verification Flow'")
    else:
        outcome = run_openlane(args.verilog_path, args.module_name, args.clock_port, args.clock_period_ns)
        print(outcome)
