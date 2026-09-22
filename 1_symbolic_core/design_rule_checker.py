"""
design_rule_checker.py
--------------------------
Fast, dependency-free static checks run *before* a genome is sent to
Verilator/Yosys. Catching obviously-broken mutants here (unbalanced
begin/end, empty case body, duplicate assignment to the same signal in one
always block) saves an expensive compile+simulate+synthesize round trip and
lets the GA loop run through more generations per hour.

This is a heuristic pre-filter, not a substitute for a real linter -- it
will not catch every DRC violation a full tool (e.g. Verilator's own
`-Wall`) would. Anything that passes here still goes through the real
compiler downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class DRCReport:
    passed: bool
    violations: List[str] = field(default_factory=list)

    def __bool__(self):
        return self.passed


def check_balanced_begin_end(source: str) -> List[str]:
    begins = len(re.findall(r"\bbegin\b", source))
    ends = len(re.findall(r"\bend\b", source))
    if begins != ends:
        return [f"unbalanced begin/end: {begins} begin(s) vs {ends} end(s)"]
    return []


def check_nonempty_case_branches(source: str) -> List[str]:
    violations = []
    for i, line in enumerate(source.splitlines()):
        stripped = line.strip()
        # Generalized from `3'b[01]{3}` so any bit-width case selector
        # (e.g. 4'b for picorv32_alu) is recognized, not just 3-bit opcodes.
        m = re.match(r"(\d+'b[01]+|default):\s*;?\s*$", stripped)
        if m:
            violations.append(f"line {i}: empty case branch for {m.group(1)}")
    return violations


def check_multiple_drivers(source: str) -> List[str]:
    """
    Heuristic: flag a signal that is assigned via both a continuous `assign`
    and inside an `always` block -- a classic multiple-driver bug.
    """
    assign_targets = set(re.findall(r"assign\s+(\w+)\s*=", source))
    always_block_match = re.search(r"always\s*@\s*\([^)]*\)\s*begin(.*?)\bend\b", source, re.DOTALL)
    always_targets = set()
    if always_block_match:
        body = always_block_match.group(1)
        always_targets = set(re.findall(r"(\w+)\s*(?:<=|=)", body))

    overlap = assign_targets & always_targets
    if overlap:
        return [f"signal(s) driven by both assign and always block: {', '.join(sorted(overlap))}"]
    return []


def check_unconnected_output(source: str, expected_outputs: List[str] | None = None) -> List[str]:
    """
    Heuristic: for each declared `output`, confirm it is assigned somewhere
    in the body. expected_outputs can be passed explicitly (e.g. from
    constraint_extractor) to avoid re-parsing the port list here.
    """
    outputs = expected_outputs or re.findall(r"output\s+(?:reg|wire)?\s*(?:\[\d+:\d+\])?\s*(\w+)", source)
    violations = []
    for out in outputs:
        if not re.search(rf"\b{re.escape(out)}\s*(?:<=|=)", source):
            violations.append(f"output '{out}' is declared but never assigned")
    return violations


def check_no_infinite_for(source: str) -> List[str]:
    """Flag `for` loops with no visible bound change -- a common cause of
    simulator hangs that process_guard would otherwise have to time out on."""
    violations = []
    for m in re.finditer(r"for\s*\([^;]*;\s*([^;]*)\s*;\s*([^)]*)\)", source):
        cond, step = m.group(1), m.group(2)
        if step.strip() == "":
            violations.append(f"for-loop with empty step clause near offset {m.start()} (possible infinite loop)")
    return violations


CHECKS = [
    check_balanced_begin_end,
    check_nonempty_case_branches,
    check_multiple_drivers,
    check_no_infinite_for,
]


def run_all_checks(source: str, expected_outputs: List[str] | None = None) -> DRCReport:
    violations: List[str] = []
    for check in CHECKS:
        violations.extend(check(source))
    violations.extend(check_unconnected_output(source, expected_outputs))
    return DRCReport(passed=(len(violations) == 0), violations=violations)


if __name__ == "__main__":
    from pathlib import Path
    seed = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    report = run_all_checks(seed.read_text())
    print(report)
