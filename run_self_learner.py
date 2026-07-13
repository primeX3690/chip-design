#!/usr/bin/env python3
"""
run_self_learner.py
----------------------
Master switch. Run this file and the evolutionary loop starts:

    python run_self_learner.py
    python run_self_learner.py --config config/system_config.yaml
    python run_self_learner.py --generations 50 --population 32

Requires Verilator and Yosys on PATH (see README.md "Environment Setup").
Use --check-tools to verify your environment before committing to a full run.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT / "4_self_improve_loop"))
sys.path.append(str(PROJECT_ROOT / "1_symbolic_core"))

from evolution_orchestrator import EvolutionOrchestrator  # noqa: E402


def setup_logging(verbose: bool):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def check_tools(config: dict) -> bool:
    ok = True
    for tool_key, label in [("verilator_bin", "Verilator"), ("yosys_bin", "Yosys")]:
        binary = config.get(tool_key, tool_key.split("_")[0])
        path = shutil.which(binary)
        if path:
            print(f"[OK] {label} found at {path}")
        else:
            print(f"[MISSING] {label} ('{binary}') not found on PATH.")
            print(f"          Install it -- see README.md 'Environment Setup'.")
            ok = False
    return ok


def apply_auto_baseline(config: dict):
    """If configured, profile the seed design with Yosys to set realistic
    area/delay normalization targets instead of the generic defaults."""
    if not config.get("auto_baseline", False):
        return config
    try:
        from constraint_extractor import extract_constraints  # noqa
        seed_path = PROJECT_ROOT / config.get("seed_design", "designs/seed/alu_basic.v")
        source = seed_path.read_text()
        constraints = extract_constraints(source, config.get("module_name", "alu_basic"), yosys_bin=config.get("yosys_bin", "yosys"))
        config["baseline_cells"] = constraints.baseline_cells
        config["baseline_depth"] = constraints.baseline_depth
        logging.getLogger("EvoHDL").info(
            "Auto-baseline: cells=%d depth=%d (%s)",
            constraints.baseline_cells, constraints.baseline_depth, constraints.notes or "profiled from seed",
        )
    except Exception as e:  # noqa: BLE001
        logging.getLogger("EvoHDL").warning("Auto-baseline profiling skipped: %s", e)
    return config


def main():
    parser = argparse.ArgumentParser(description="EvoHDL master switch")
    parser.add_argument("--config", default="config/system_config.yaml")
    parser.add_argument("--generations", type=int, default=None, help="override generations from config")
    parser.add_argument("--population", type=int, default=None, help="override population_size from config")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--check-tools", action="store_true", help="verify Verilator/Yosys are installed and exit")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("EvoHDL")

    config = load_config(args.config)

    if args.check_tools:
        ok = check_tools(config)
        sys.exit(0 if ok else 1)

    if not check_tools(config):
        logger.error("Missing required EDA tools. Run with --check-tools for details, or see README.md.")
        sys.exit(1)

    if args.generations is not None:
        config["generations"] = args.generations
    if args.population is not None:
        config["population_size"] = args.population

    config = apply_auto_baseline(config)

    logger.info("Starting EvoHDL run: %s", config.get("module_name"))
    orchestrator = EvolutionOrchestrator(config)
    best = orchestrator.run()

    logger.info("Run complete.")
    logger.info("Best fitness: %.4f", best.fitness)
    logger.info("Best design saved to designs/best/%s_best.v", config.get("module_name"))
    logger.info("Run history saved to dashboard/run_history.json")
    logger.info("Launch the dashboard with: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
