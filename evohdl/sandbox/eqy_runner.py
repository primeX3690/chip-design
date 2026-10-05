"""
eqy_runner.py -- optional bridge to YosysHQ `eqy` (Equivalence Checking with Yosys).

eqy is a separate tool (`eqy`, plus `sby` + an SMT solver for the sequential strategy). If it is not installed
this module reports "not installed" and the formal pipeline simply skips it -- nothing else depends on it.

The generated config follows eqy's documented layout ([gold]/[gate]/[strategy] sections). I could not run eqy in
the environment where this was written, so treat the exact config as "to be confirmed on your machine":
`python -m evohdl.sandbox.formal_pipeline --selftest` exercises it when eqy is on PATH, and the generated
`.eqy` file is kept next to the report (--keep-workdir) so you can adjust it by hand if your eqy version differs.
Hierarchy is flattened per side inside each [gold]/[gate] script, so identically named sub-modules don't collide.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from evohdl.sandbox.equivalence_checker import EquivalenceOutcome, _autodetect, is_sequential
from evohdl.sandbox.process_guard import run_guarded

EQY_PASS_RE = re.compile(r"DONE \(PASS|Successfully proved designs equivalent", re.IGNORECASE)
EQY_FAIL_RE = re.compile(r"DONE \(FAIL|Failed to prove equivalence|unproven", re.IGNORECASE)


def eqy_available(eqy_bin: str = "eqy") -> bool:
    return shutil.which(eqy_bin) is not None


def build_eqy_config(module_name: str, sv: bool, hierarchical: bool, strategy: str = "sat", depth: int = 10) -> str:
    read = "read_verilog -sv" if sv else "read_verilog"
    flat = "\nflatten" if hierarchical else ""
    use = "sby" if strategy == "sby" else "sat"
    engine = "\nengine smtbmc" if strategy == "sby" else ""
    return f"""[gold]
{read} gold.v
prep -top {module_name}{flat}

[gate]
{read} gate.v
prep -top {module_name}{flat}

[strategy {strategy}]
use {use}
depth {depth}{engine}
"""


def check_equivalence_eqy(
    seed_verilog: str,
    evolved_verilog: str,
    module_name: str,
    eqy_bin: str = "eqy",
    timeout_sec: float = 300.0,
    sv: bool | None = None,
    hierarchical: bool | None = None,
    strategy: str | None = None,
    depth: int = 10,
    keep_workdir: bool = False,
) -> EquivalenceOutcome:
    """Run eqy. equivalent=True ONLY on an explicit PASS from eqy. Result `log` carries the strategy/depth used."""
    if not eqy_available(eqy_bin):
        return EquivalenceOutcome(checked=False, error="[eqy not installed] skipped")
    sv, hierarchical = _autodetect(seed_verilog, evolved_verilog, sv, hierarchical)
    seq = is_sequential(seed_verilog) or is_sequential(evolved_verilog)
    if strategy is None:
        strategy = "sby" if (seq and shutil.which("sby")) else "sat"
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_eqy_"))
    try:
        (workdir / "gold.v").write_text(seed_verilog)
        (workdir / "gate.v").write_text(evolved_verilog)
        cfg = workdir / "check.eqy"
        cfg.write_text(build_eqy_config(module_name, sv, hierarchical, strategy, depth))
        result = run_guarded([eqy_bin, "-f", "-d", str(workdir / "eqy_out"), str(cfg)],
                             timeout_sec=timeout_sec, cwd=str(workdir))
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        note = f"eqy strategy={strategy} depth={depth}"
        if not result.timed_out and result.returncode == 0 and EQY_PASS_RE.search(combined):
            return EquivalenceOutcome(checked=True, equivalent=True, bounded=(strategy == "sat" and seq),
                                      seq_cycles=depth if seq else 0, log=f"{note}\n{combined[-1800:]}")
        if not result.timed_out and EQY_FAIL_RE.search(combined):
            return EquivalenceOutcome(checked=True, equivalent=False, log=f"{note}\n{combined[-1800:]}")
        reason = "timeout" if result.timed_out else "eqy error"
        return EquivalenceOutcome(checked=False, error=f"[{reason}] {combined[-1200:]}", log=note)
    finally:
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
