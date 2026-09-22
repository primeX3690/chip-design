"""
hardware_verification_pipeline.py
------------------------------------
Runs ONCE, after the GA finishes, on the single best genome
(designs/best/<module>_best.v). Chains together every "make it real"
upgrade in order, and writes one consolidated, investor-ready report:

  1. baseline_compare   -- generic Yosys `synth` proxy: cell count + logic
                            depth, seed vs evolved (fast, always available).
  2. openlane_runner     -- real synthesis + place + route on the actual
                            open SkyWater 130nm PDK (sky130_fd_sc_hd):
                            real die area in um^2.
  3. opensta_runner      -- real static timing analysis against the sky130
                            liberty timing model on OpenLane's routed
                            netlist: real picosecond-level worst-case delay.
  4. nextpnr_runner      -- real FPGA (iCE40) place-and-route, no board
                            needed: real routed congestion (LUT/carry
                            utilization) and real routed critical-path
                            delay, as an independent second silicon-adjacent
                            data point alongside the ASIC (sky130) numbers.

Steps 2-3 need Docker + the sky130 PDK + a built OpenSTA binary, none of
which are available in every environment (they are NOT part of this
repo's pip requirements -- see README.md "Real Hardware Verification
Flow"). This pipeline runs whatever is available and clearly marks
anything it had to skip in the final report -- it never fabricates a
number for a tool it couldn't run.

Usage:
    python 4_self_improve_loop/hardware_verification_pipeline.py \
        --module picorv32_alu \
        --baseline designs/seed/picorv32_alu.v \
        --evolved designs/best/picorv32_alu_best.v

or:
    python run_self_learner.py --config config/config_picorv32_alu.yaml --full-verify
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "2_evolutionary_engine"))
sys.path.append(str(PROJECT_ROOT / "4_self_improve_loop"))

from baseline_compare import compare_to_baseline  # noqa: E402
from openlane_runner import run_openlane, openlane_available  # noqa: E402
from opensta_runner import run_sta, opensta_available, find_sky130_liberty  # noqa: E402
from nextpnr_runner import run_nextpnr, nextpnr_available  # noqa: E402

logger = logging.getLogger("EvoHDL.hardware_verification_pipeline")

REPORT_DIR = PROJECT_ROOT / "benchmarks"


def run_full_verification(
    module_name: str,
    baseline_rtl_path: str,
    evolved_rtl_path: str,
    clock_port: str | None = None,
    clock_period_ns: float = 10.0,
    yosys_bin: str = "yosys",
    sta_bin: str = "sta",
    pdk_root: str = "~/.volare",
) -> dict:
    report: dict = {
        "module_name": module_name,
        "baseline_rtl_path": baseline_rtl_path,
        "evolved_rtl_path": evolved_rtl_path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stages": {},
    }

    # -- Stage 1: generic Yosys proxy (always runs, this is the fast metric
    # the GA itself optimizes against) -----------------------------------
    logger.info("Stage 1/4: generic Yosys baseline vs evolved comparison")
    try:
        generic = compare_to_baseline(baseline_rtl_path, evolved_rtl_path, module_name, yosys_bin)
        report["stages"]["generic_synth"] = {"ran": True, **generic}
    except Exception as e:  # noqa: BLE001
        report["stages"]["generic_synth"] = {"ran": False, "error": str(e)}

    # -- Stage 2: real OpenLane + sky130 P&R on the evolved design --------
    logger.info("Stage 2/4: OpenLane + SkyWater130 (real ASIC area)")
    if openlane_available():
        outcome = run_openlane(evolved_rtl_path, module_name, clock_port, clock_period_ns)
        report["stages"]["openlane_sky130"] = outcome.__dict__
    else:
        report["stages"]["openlane_sky130"] = {
            "ran": False,
            "error": "Docker not found -- install Docker + `pip install volare` and run "
                     "`volare enable <pdk-version>` first (see README.md).",
        }

    # -- Stage 3: real OpenSTA timing on OpenLane's routed netlist ---------
    logger.info("Stage 3/4: OpenSTA (real picosecond timing)")
    ol_stage = report["stages"]["openlane_sky130"]
    if opensta_available() and ol_stage.get("ran"):
        liberty = find_sky130_liberty(pdk_root)
        run_dir = Path(ol_stage["run_dir"])
        netlist_candidates = list(run_dir.glob("**/*.nl.v")) + list(run_dir.glob("**/*.v"))
        if liberty and netlist_candidates:
            sta_outcome = run_sta(netlist_candidates[0], module_name, liberty, clock_port, clock_period_ns, sta_bin)
            report["stages"]["opensta"] = sta_outcome.__dict__
        else:
            report["stages"]["opensta"] = {"ran": False, "error": "no sky130 liberty file or routed netlist found"}
    else:
        reason = "OpenSTA ('sta') not on PATH" if not opensta_available() else "OpenLane stage didn't produce a netlist to analyze"
        report["stages"]["opensta"] = {"ran": False, "error": reason}

    # -- Stage 4: real nextpnr FPGA P&R (independent of Docker/PDK) -------
    logger.info("Stage 4/4: nextpnr-ice40 (real FPGA place-and-route)")
    if nextpnr_available():
        pnr_outcome = run_nextpnr(evolved_rtl_path, module_name, target_freq_mhz=1000.0 / clock_period_ns)
        report["stages"]["nextpnr_ice40"] = pnr_outcome.__dict__
    else:
        report["stages"]["nextpnr_ice40"] = {
            "ran": False,
            "error": "yosys and/or nextpnr-ice40 not on PATH (apt install nextpnr-ice40 on Debian/Ubuntu/WSL2).",
        }

    return report


def render_markdown(report: dict) -> str:
    m = report["module_name"]
    lines = [
        f"# EvoHDL Hardware Verification Report -- {m}",
        "",
        f"Generated: {report['generated_at']}",
        f"Baseline (human-written reference): `{report['baseline_rtl_path']}`",
        f"Evolved (GA best individual): `{report['evolved_rtl_path']}`",
        "",
        "## 1. Generic synthesis (Yosys `synth`, technology-independent)",
        "",
    ]

    gs = report["stages"].get("generic_synth", {})
    if gs.get("ran"):
        lines += [
            "| Metric | Baseline | Evolved | Improvement |",
            "|---|---|---|---|",
            f"| Cell count | {gs['baseline_cell_count']:.0f} | {gs['evolved_cell_count']:.0f} | "
            f"{gs['cell_count_improvement_pct']:+.1f}% |" if gs.get('cell_count_improvement_pct') is not None else "n/a",
            f"| Logic depth (levels) | {gs['baseline_logic_depth']:.0f} | {gs['evolved_logic_depth']:.0f} | "
            f"{gs['logic_depth_improvement_pct']:+.1f}% |" if gs.get('logic_depth_improvement_pct') is not None else "n/a",
        ]
    else:
        lines.append(f"_Not available: {gs.get('error', 'unknown error')}_")

    lines += ["", "## 2. Real ASIC flow -- OpenLane + SkyWater 130nm (sky130_fd_sc_hd)", ""]
    ol = report["stages"].get("openlane_sky130", {})
    if ol.get("ran"):
        lines += [
            f"- **Die area:** {ol['die_area_um2']:.1f} um^2",
            f"- **Core area:** {ol['core_area_um2']:.1f} um^2",
            f"- **Instance count:** {ol['cell_count']}",
            f"- **Worst setup slack:** {ol.get('worst_setup_slack_ns', 'n/a')} ns",
            f"- **Worst hold slack:** {ol.get('worst_hold_slack_ns', 'n/a')} ns",
            f"- Run directory: `{ol['run_dir']}`",
        ]
    else:
        lines.append(f"_Not available: {ol.get('error', 'unknown error')}_")

    lines += ["", "## 3. Real static timing analysis -- OpenSTA (sky130 liberty)", ""]
    sta = report["stages"].get("opensta", {})
    if sta.get("ran"):
        lines += [
            f"- **Critical path delay:** {sta.get('critical_path_delay_ps', 'n/a')} ps",
            f"- **Worst negative slack:** {sta.get('worst_negative_slack_ps', 'n/a')} ps",
            f"- **Total negative slack:** {sta.get('total_negative_slack_ps', 'n/a')} ps",
        ]
    else:
        lines.append(f"_Not available: {sta.get('error', 'unknown error')}_")

    lines += ["", "## 4. Real FPGA place-and-route -- nextpnr-ice40 (no board required)", ""]
    pnr = report["stages"].get("nextpnr_ice40", {})
    if pnr.get("ran"):
        lines += [
            f"- **Routed critical path:** {pnr.get('critical_path_ns', 'n/a'):.2f} ns"
            if pnr.get('critical_path_ns') is not None else "- Routed critical path: n/a",
            f"- **Implied max frequency:** {pnr.get('implied_fmax_mhz', 'n/a'):.1f} MHz"
            if pnr.get('implied_fmax_mhz') is not None else "- Implied max frequency: n/a",
            f"- **Logic cells used:** {pnr['logic_cells_used']} / {pnr['logic_cells_available']}",
            f"- **I/O used:** {pnr['io_used']} / {pnr['io_available']}",
        ]
    else:
        lines.append(f"_Not available: {pnr.get('error', 'unknown error')}_")

    lines += [
        "",
        "---",
        "_Stages 1 and 4 run on any machine with Yosys + Verilator + nextpnr-ice40 "
        "installed (all apt-installable). Stages 2-3 need Docker + the sky130 PDK "
        "(via `volare`) + a built OpenSTA binary -- see README.md 'Real Hardware "
        "Verification Flow' for setup. Any stage marked 'Not available' above was "
        "skipped, not faked -- rerun after installing its tool to fill it in._",
    ]
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the full real-hardware verification pipeline on a GA result")
    parser.add_argument("--module", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--evolved", required=True)
    parser.add_argument("--clock-port", default=None)
    parser.add_argument("--clock-period-ns", type=float, default=10.0)
    parser.add_argument("--yosys-bin", default="yosys")
    parser.add_argument("--sta-bin", default="sta")
    parser.add_argument("--pdk-root", default="~/.volare")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    report = run_full_verification(
        args.module, args.baseline, args.evolved,
        args.clock_port, args.clock_period_ns, args.yosys_bin, args.sta_bin, args.pdk_root,
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "hardware_verification_report.json"
    md_path = REPORT_DIR / "hardware_verification_report.md"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    md_path.write_text(render_markdown(report))

    print(f"Report written to {json_path} and {md_path}")


if __name__ == "__main__":
    main()
