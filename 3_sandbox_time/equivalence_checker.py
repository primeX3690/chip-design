"""
equivalence_checker.py
-----------------------
Stage-4 addition (2026-09): formal equivalence checking between the seed
design and an evolved mutant, using Yosys's built-in `miter` + `sat`
commands (no external `eqy`/SymbiYosys install needed -- just the Yosys
binary the rest of the pipeline already requires).

WHY THIS EXISTS
The GA pipeline currently only accepts a mutant as "functionally correct"
if it passes a finite set of simulation test vectors (200 by default).
That's simulation-based confidence, not a proof: a mutant could pass every
generated vector yet still differ from the seed on some untested input.
For a pitch or for anything safety-adjacent, that gap matters. This module
adds a genuine formal check -- SAT-based logical equivalence -- as an
*additional*, optional gate before a design is accepted as the final
"best" result, on top of (not replacing) the existing simulation testing.

WHAT IT ACTUALLY PROVES
- Combinational designs (alu_basic, picorv32_alu): a real, unbounded proof.
  If `sat -verify -prove trigger 0` returns UNSAT, the two circuits are
  logically equivalent for *every* possible input, not just the ones
  simulated. This is the same class of check `eqy`/`equiv_opt` perform,
  built from Yosys's lower-level primitives directly.
- Sequential designs (counter_4bit and friends): this checks equivalence
  over a *bounded* number of clock cycles (`--seq-cycles`), starting from
  reset. That is a strong, real check (it will catch essentially any
  mutation that breaks the counter's behaviour within that horizon) but
  it is NOT an unbounded inductive proof of equivalence for all time --
  full sequential equivalence (k-induction) is out of scope for stock
  Yosys and would need SymbiYosys/eqy. Treat SEQUENTIAL results as strong
  evidence, not the same ironclad guarantee as the combinational case, and
  say so honestly in anything derived from this (a pitch deck included).

This module never raises -- every failure mode collapses into
EquivalenceOutcome so a caller can log-and-continue rather than crash a
GA run over a flaky toolchain invocation.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import logging
from dataclasses import dataclass
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from process_guard import run_guarded  # noqa: E402

logger = logging.getLogger("EvoHDL.equivalence_checker")

# Yosys prints one of these once the SAT engine finishes:
#   "SAT proof finished - no model found: SUCCESS!"   -> UNSAT -> equivalent
#   "SAT proof finished - model found: FAIL!"           -> SAT   -> a real
#                                                          counterexample
#                                                          exists -> NOT
#                                                          equivalent
PROOF_UNSAT_RE = re.compile(r"SAT proof finished.*no model found", re.IGNORECASE | re.DOTALL)
PROOF_SAT_RE = re.compile(r"SAT proof finished.*model found", re.IGNORECASE | re.DOTALL)


@dataclass
class EquivalenceOutcome:
    checked: bool          # did the tool run to completion at all
    equivalent: bool = False
    bounded: bool = False   # True for sequential (bounded-cycles) checks
    seq_cycles: int = 0
    log: str = ""
    error: str = ""

    @property
    def inconclusive(self) -> bool:
        """True when Yosys ran but neither UNSAT nor SAT could be parsed out
        (e.g. it gave up / timed out inside the SAT engine itself). Callers
        should treat this the same as "not proven equivalent" -- never
        upgrade an inconclusive result to a pass."""
        return self.checked and not self.equivalent and not self.error


def _build_combinational_script(module_name: str, seed_path: Path, evolved_path: Path) -> str:
    return f"""
read_verilog {seed_path.as_posix()}
rename {module_name} gold
read_verilog {evolved_path.as_posix()}
rename {module_name} gate
proc; opt_clean
miter -equiv -flatten -make_outputs gold gate miter
hierarchy -top miter
flatten miter
sat -verify -prove trigger 0 -set-init-undef -ignore_div_by_zero -show-inputs -show-outputs miter
"""


def _build_sequential_script(module_name: str, seed_path: Path, evolved_path: Path, seq_cycles: int) -> str:
    # -seq N bounds the check to N clock cycles from a reset state instead
    # of proving equivalence for all time (see module docstring).
    return f"""
read_verilog {seed_path.as_posix()}
rename {module_name} gold
read_verilog {evolved_path.as_posix()}
rename {module_name} gate
proc; opt_clean
miter -equiv -flatten -make_outputs gold gate miter
hierarchy -top miter
flatten miter
sat -verify -prove trigger 0 -set-init-undef -ignore_div_by_zero -show-inputs -show-outputs -seq {seq_cycles} miter
"""


def check_equivalence(
    seed_verilog: str,
    evolved_verilog: str,
    module_name: str = "alu_basic",
    sequential: bool = False,
    seq_cycles: int = 20,
    yosys_bin: str = "yosys",
    timeout_sec: float = 60.0,
) -> EquivalenceOutcome:
    """
    Formally (SAT) check whether `evolved_verilog` is logically equivalent
    to `seed_verilog` for the same module_name/port contract.

    Only meaningful when both designs share the exact same port list (which
    is guaranteed by this repo's mutation model -- mutation/crossover never
    touch the interface, only the implementation inside the module -- see
    testbench_generator.py's module docstring).
    """
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_equiv_"))
    try:
        seed_path = workdir / "seed.v"
        evolved_path = workdir / "evolved.v"
        seed_path.write_text(seed_verilog)
        evolved_path.write_text(evolved_verilog)

        script = (
            _build_sequential_script(module_name, seed_path, evolved_path, seq_cycles)
            if sequential
            else _build_combinational_script(module_name, seed_path, evolved_path)
        )
        script_path = workdir / "equiv.ys"
        script_path.write_text(script)

        result = run_guarded(
            [yosys_bin, "-Q", "-T", "-s", str(script_path)],
            timeout_sec=timeout_sec,
            cwd=str(workdir),
        )

        # BUG FIX (2026-09): `sat -verify` makes Yosys exit NON-ZERO when the
        # proof fails ("ERROR: Called with -verify and proof did fail!"), i.e.
        # exactly when a real counterexample exists. The old code treated any
        # non-zero exit as a tool failure (checked=False) and never looked at
        # the verdict, so a genuine "NOT equivalent" was mislabeled as an
        # inconclusive tool error. Check the SAT verdict in the output first.
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        if not result.timed_out and not PROOF_UNSAT_RE.search(combined) and (
            PROOF_SAT_RE.search(combined) or "proof did fail" in combined
        ):
            return EquivalenceOutcome(
                checked=True, equivalent=False, bounded=sequential,
                seq_cycles=seq_cycles if sequential else 0,
                log=combined[-4000:],
                error="SAT solver found a real counterexample -- designs differ (see log for the failing inputs/outputs).",
            )

        if not result.ok:
            reason = "timeout" if result.timed_out else "yosys/sat error"
            return EquivalenceOutcome(
                checked=False,
                bounded=sequential,
                seq_cycles=seq_cycles if sequential else 0,
                error=f"[{reason}] {result.stderr[-1500:] or result.stdout[-1500:]}",
                log=result.stdout[-2000:],
            )

        out = result.stdout
        if PROOF_UNSAT_RE.search(out):
            return EquivalenceOutcome(
                checked=True, equivalent=True, bounded=sequential,
                seq_cycles=seq_cycles if sequential else 0, log=out[-2000:],
            )
        if PROOF_SAT_RE.search(out):
            return EquivalenceOutcome(
                checked=True, equivalent=False, bounded=sequential,
                seq_cycles=seq_cycles if sequential else 0, log=out[-2000:],
                error="SAT solver found a real counterexample -- designs differ.",
            )
        # Yosys ran without crashing but we couldn't parse a definitive
        # verdict out of its output -- never guess; report inconclusive.
        return EquivalenceOutcome(
            checked=True, equivalent=False, bounded=sequential,
            seq_cycles=seq_cycles if sequential else 0, log=out[-2000:],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    # Smoke test: a design should always be equivalent to itself.
    demo_path = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    if demo_path.exists():
        src = demo_path.read_text()
        outcome = check_equivalence(src, src, module_name="alu_basic")
        print(outcome)
    else:
        print("Seed design not found for smoke test.")
