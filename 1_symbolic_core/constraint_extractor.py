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
# (yosys_synthesizer.synthesize_design is imported lazily inside
# extract_constraints() to avoid a circular-import risk at module load time)

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
    # BUG FIX (2026-09): this used to run its OWN, slightly different Yosys
    # script (missing the `fsm`/`memory` opt passes and, critically, the
    # final `opt_clean` that yosys_synthesizer.py's live per-individual
    # scoring always runs). That mismatch meant "baseline_cells" profiled
    # here for a fresh module never actually matched what score() measures
    # for the IDENTICAL seed genome during the GA run -- so even an
    # unmutated, exactly-tied-to-baseline individual scored a fitness below
    # the correct value of 1.0 (confirmed: a real 40-generation
    # picorv32_alu run reported baseline_compare.py cell_count/logic_depth
    # tied exactly 1318=1318 / 23=23, yet best_fitness was 0.8522, not
    # 1.0 -- and that number never moved from generation 0's value at all).
    # Now both paths call the exact same synthesize_design(), so
    # baseline_cells/baseline_depth are always measured identically to how
    # every individual is scored -- a tied design is guaranteed fitness=1.0.
    sys.path.append(str(Path(__file__).resolve().parent.parent / "3_sandbox_time"))
    from yosys_synthesizer import synthesize_design  # noqa: E402

    ports = extract_ports(verilog_source)
    outcome = synthesize_design(verilog_source, module_name=module_name, yosys_bin=yosys_bin, timeout_sec=timeout_sec)

    if not outcome.synthesized:
        return DesignConstraints(
            module_name=module_name,
            ports=ports,
            baseline_cells=40,
            baseline_wires=20,
            baseline_depth=6,
            notes=f"yosys unavailable or failed ({outcome.error[:200]}); using generic defaults",
        )

    return DesignConstraints(
        module_name=module_name,
        ports=ports,
        baseline_cells=outcome.cell_count or 40,
        baseline_wires=outcome.wire_count or 20,
        baseline_depth=outcome.logic_depth or 6,
    )


if __name__ == "__main__":
    seed = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    c = extract_constraints(seed.read_text(), "alu_basic")
    print(c)

