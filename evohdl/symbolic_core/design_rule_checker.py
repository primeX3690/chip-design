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
from evohdl.paths import SEED_DIR


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


_OUTPUT_DECL_RE = re.compile(
    r"\boutput\s+(?:(?:reg|wire|logic|signed|unsigned|var)\s+)*(?:\[[^\]]+\]\s*)*(\w+)"
)


def _is_driven(name: str, source: str) -> bool:
    n = re.escape(name)
    return bool(
        re.search(rf"\b{n}\b\s*(?:\[[^\]]*\]\s*)?(?:<=|=)(?!=)", source)        # plain / bit-select assignment
        or re.search(rf"\{{[^}}]*\b{n}\b[^}}]*\}}\s*(?:<=|=)(?!=)", source)         # concatenation on the LHS
        or re.search(rf"\.\w+\s*\(\s*[^()]*\b{n}\b[^()]*\)", source)               # driven by a sub-module port
    )


def check_unconnected_output(source: str, expected_outputs: List[str] | None = None) -> List[str]:
    """
    Heuristic: for each declared `output`, confirm it is assigned somewhere in the body
    (assignment, concatenation target, or a sub-module port connection -- so hierarchical and
    SystemVerilog `output logic [N:0] x` ports are handled). expected_outputs can be passed
    explicitly (e.g. from constraint_extractor) to avoid re-parsing the port list here.
    """
    outputs = expected_outputs or _OUTPUT_DECL_RE.findall(source)
    violations = []
    for out in outputs:
        if not _is_driven(out, source):
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


def analyze_design_support(source: str, module_name: str | None = None,
                           verification_mode: str | None = None) -> List[str]:
    """Pre-flight: say up front what this seed design will and won't support.

    The text mutators are regex-based, not a Verilog parser (see README "Current
    limitations"). Rather than silently no-op on unsupported structure, report it.
    Messages are prefixed "ERROR:" (run cannot work), "WARN:" (works, reduced) or "INFO:".
    """
    from evohdl.sandbox.testbench_generator import MODULE_RENDERERS  # local: avoid import cycle at load
    from evohdl.sandbox.design_bundle import count_modules, looks_like_systemverilog

    msgs: List[str] = []
    n_modules = count_modules(source)
    if n_modules > 1:
        msgs.append(f"INFO: {n_modules} modules (hierarchy) -- flattened for synthesis and equivalence checking")
    if module_name and module_name in MODULE_RENDERERS:
        # Reward-hacking guard: an output the testbench never reads can be broken for free (the GA once "optimized"
        # alu_basic by deleting zero_flag). Flag any declared output that the rendered testbench never touches.
        from evohdl.sandbox.testbench_generator import render_testbench
        tb = render_testbench(module_name)
        unobserved = [o for o in _OUTPUT_DECL_RE.findall(source) if f"dut->{o}" not in tb]
        if unobserved:
            sev = "ERROR" if verification_mode in (None, "simulation") else "WARN"
            msgs.append(f"{sev}: output(s) {unobserved} are never checked by the '{module_name}' testbench -- the GA can "
                        f"delete that logic for free (reward hacking). Fix the testbench"
                        + ("" if sev == "ERROR" else "; only formal equivalence protects them in this mode"))
    if module_name and module_name not in MODULE_RENDERERS:
        if verification_mode in (None, "simulation"):
            msgs.append(f"ERROR: no testbench renderer registered for '{module_name}' "
                        f"(known: {sorted(MODULE_RENDERERS)}) -- use verification_mode: formal")
        else:
            msgs.append(f"WARN: no testbench renderer for '{module_name}'; correctness relies on formal "
                        f"equivalence to the seed only (no simulation fallback)")
    if looks_like_systemverilog(source):
        msgs.append("WARN: SystemVerilog -- read with Yosys' built-in frontend (`read_verilog -sv`); "
                    "interfaces/classes/advanced packages are not supported; regex mutators target Verilog-2001 style")
    if re.search(r"\bgenerate\b", source):
        msgs.append("WARN: generate blocks are not understood by the regex mutators")
    if re.search(r"always(?:_ff)?\s*@\s*\(\s*(posedge|negedge)", source):
        msgs.append("WARN: sequential logic -- equivalence uses equiv_make (needs matching register names); "
                    "unproven results fall back to simulation in hybrid mode")
    if not _CASE_BRANCH_RE.search(source):
        msgs.append("WARN: no `N'bXXX:` case branches -- operator/constant/shift mutators will mostly "
                    "no-op; the Yosys pass pipelines, resynth and algebraic rewrites can still change this design")
    return msgs


_CASE_BRANCH_RE = re.compile(r"^\s*\d+'b[01]+\s*:", re.MULTILINE)


if __name__ == "__main__":
    from pathlib import Path
    seed = SEED_DIR / "alu_basic.v"
    report = run_all_checks(seed.read_text())
    print(report)
