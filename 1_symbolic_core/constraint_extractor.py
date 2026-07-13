"""
constraint_extractor.py
--------------------------
Runs a lightweight Yosys pass over a reference design to extract baseline
constraints (port list, cell count, wire count) used to normalize fitness
scoring (see fitness_evaluator.BASELINE_CELLS / BASELINE_DEPTH) and to seed
config/system_config.yaml with sane defaults for a new design.

This is intentionally separate from yosys_synthesizer.py: that module scores
*mutant* designs during the GA loop, this one profiles the *seed* design once
at startup.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List

sys.path.append(str(Path(__file__).resolve().parent.parent / "3_sandbox_time"))
from process_guard import run_guarded  # noqa: E402

PORT_RE = re.compile(r"(input|output)\s+(reg|wire)?\s*(\[\d+:\d+\])?\s*(\w+)")


@dataclass
class DesignConstraints:
    module_name: str
    ports: List[str]
    baseline_cells: int
    baseline_wires: int
    baseline_depth: int
    notes: str = ""


def extract_ports(verilog_source: str) -> List[str]:
    """Best-effort static extraction of port names from a module declaration."""
    ports = []
    in_ports = False
    for line in verilog_source.splitlines():
        if re.search(r"\bmodule\s+\w+\s*\(", line):
            in_ports = True
        if in_ports:
            m = PORT_RE.search(line)
            if m:
                ports.append(m.group(4))
        if in_ports and ");" in line:
            break
    return ports


def extract_constraints(
    verilog_source: str,
    module_name: str,
    yosys_bin: str = "yosys",
    timeout_sec: float = 30.0,
) -> DesignConstraints:
    import tempfile
    import shutil

    workdir = Path(tempfile.mkdtemp(prefix="evohdl_constraints_"))
    try:
        design_path = workdir / f"{module_name}.v"
        design_path.write_text(verilog_source)
        script = f"""
read_verilog {design_path.as_posix()}
hierarchy -check -top {module_name}
proc; opt; techmap; opt
synth -top {module_name}
stat
ltp
"""
        script_path = workdir / "constraints.ys"
        script_path.write_text(script)

        result = run_guarded([yosys_bin, "-Q", "-T", "-s", str(script_path)], timeout_sec=timeout_sec, cwd=str(workdir))
        ports = extract_ports(verilog_source)

        if not result.ok:
            return DesignConstraints(
                module_name=module_name,
                ports=ports,
                baseline_cells=40,
                baseline_wires=20,
                baseline_depth=6,
                notes=f"yosys unavailable or failed ({result.stderr[:200]}); using generic defaults",
            )

        cell_match = re.search(r"Number of cells:\s*(\d+)", result.stdout)
        wire_match = re.search(r"Number of wires:\s*(\d+)", result.stdout)
        depth_match = re.search(r"Longest topological path.*?(\d+)\s*step", result.stdout, re.IGNORECASE | re.DOTALL)

        return DesignConstraints(
            module_name=module_name,
            ports=ports,
            baseline_cells=int(cell_match.group(1)) if cell_match else 40,
            baseline_wires=int(wire_match.group(1)) if wire_match else 20,
            baseline_depth=int(depth_match.group(1)) if depth_match else 6,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    seed = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    c = extract_constraints(seed.read_text(), "alu_basic")
    print(c)
