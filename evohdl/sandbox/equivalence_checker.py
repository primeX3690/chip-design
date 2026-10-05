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

GA-LOOP USE (2026-10 addition): `check_equivalence_auto()` is what fitness_evaluator calls when
`verification_mode` is `formal` or `hybrid`. Combinational designs use the miter+SAT proof above;
sequential designs use Yosys' `equiv_make` + `equiv_simple` + `equiv_induct` flow, which can give an
UNBOUNDED proof when register names line up between seed and mutant, and otherwise reports
"unproven" (never "equivalent"). Anything unproven is NOT accepted by `formal` mode and falls back to
simulation in `hybrid` mode. SAT-based checking is fast on small/medium cones but can time out on very
wide arithmetic (e.g. multipliers); a timeout is "unproven", never a pass.

HIERARCHY: multi-module designs are flattened per side (each in its own stashed design) before the
miter is built, so seed and mutant may define identically named sub-modules.

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
from evohdl.sandbox.process_guard import run_guarded  # noqa: E402
from evohdl.paths import SEED_DIR

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


def _read_cmd(sv: bool) -> str:
    return "read_verilog -sv" if sv else "read_verilog"


def _load_pair_script(module_name: str, seed_path: Path, evolved_path: Path,
                      sv: bool = False, hierarchical: bool = False) -> str:
    """Load seed as `gold` and evolved as `gate` into one design."""
    rd = _read_cmd(sv)
    if not hierarchical:
        return f"""
{rd} {seed_path.as_posix()}
rename {module_name} gold
{rd} {evolved_path.as_posix()}
rename {module_name} gate
proc; opt_clean
"""
    # Hierarchical: each side is elaborated + flattened in its own design, so identically named
    # sub-modules in seed and mutant never collide; only the flattened tops are merged.
    return f"""
{rd} {seed_path.as_posix()}
hierarchy -check -top {module_name}
proc; flatten; opt_clean
rename {module_name} gold
design -stash gold_d
{rd} {evolved_path.as_posix()}
hierarchy -check -top {module_name}
proc; flatten; opt_clean
rename {module_name} gate
design -stash gate_d
design -copy-from gold_d -as gold gold
design -copy-from gate_d -as gate gate
"""


def _build_combinational_script(module_name: str, seed_path: Path, evolved_path: Path,
                                sv: bool = False, hierarchical: bool = False) -> str:
    return _load_pair_script(module_name, seed_path, evolved_path, sv, hierarchical) + """miter -equiv -flatten -make_outputs gold gate miter
hierarchy -top miter
flatten miter
sat -verify -prove trigger 0 -set-init-undef -ignore_div_by_zero -show-inputs -show-outputs miter
"""


def detect_reset_port(source: str):
    """Best-effort (name, active_low) of the reset input, from the port names; None if not found."""
    m = re.search(r"\binput\s+(?:wire\s+|logic\s+)?(?:\[[^\]]*\]\s*)?(\w*(?:rst|reset)\w*)", source, re.IGNORECASE)
    if not m:
        return None
    name = m.group(1)
    low = bool(re.search(r"(_n|n|_b|b)$", name, re.IGNORECASE) or re.search(r"(rst|reset)_?n", name, re.IGNORECASE))
    return name, low


def _build_sequential_script(module_name: str, seed_path: Path, evolved_path: Path, seq_cycles: int,
                             sv: bool = False, hierarchical: bool = False,
                             reset_port: str | None = None, reset_active_low: bool = True) -> str:
    # Bounded model check over `seq_cycles` clock cycles (NOT an unbounded proof).
    # async2sync + dffunmap: `sat` only models plain $dff, so async-reset / enable flops are rewritten first.
    # With a reset port, the reset is forced active in step 1 and the first step is not compared, so the check
    # starts from the RESET state instead of from arbitrary (possibly unreachable) register contents.
    reset = ""
    if reset_port:
        reset = f" -set-at 1 {reset_port} {0 if reset_active_low else 1} -prove-skip 1"
    return _load_pair_script(module_name, seed_path, evolved_path, sv, hierarchical) + f"""miter -equiv -flatten -make_outputs gold gate miter
hierarchy -top miter
flatten miter
async2sync
dffunmap
sat -verify -prove trigger 0 -set-init-undef -ignore_div_by_zero -show-inputs -show-outputs -seq {seq_cycles}{reset} miter
"""


def _build_equiv_make_script(module_name: str, seed_path: Path, evolved_path: Path,
                             sv: bool = False, hierarchical: bool = False) -> str:
    """Yosys' structural equivalence flow: pairs same-named signals/registers between gold and gate,
    then proves each pair (equiv_simple = SAT per cone, equiv_induct = inductive over registers)."""
    return _load_pair_script(module_name, seed_path, evolved_path, sv, hierarchical) + """equiv_make gold gate equiv
hierarchy -top equiv
async2sync
equiv_simple -seq 5
equiv_induct
equiv_status -assert
"""


EQUIV_PROVEN_RE = re.compile(r"Equivalence successfully proven", re.IGNORECASE)
EQUIV_UNPROVEN_RE = re.compile(r"unproven \$equiv cells", re.IGNORECASE)


def is_sequential(source: str) -> bool:
    """True if the source contains clocked always blocks (posedge/negedge sensitivity)."""
    return bool(re.search(r"always(?:_ff)?\s*@\s*\(\s*(?:posedge|negedge)", source))


def check_equivalence(
    seed_verilog: str,
    evolved_verilog: str,
    module_name: str = "alu_basic",
    sequential: bool = False,
    seq_cycles: int = 20,
    yosys_bin: str = "yosys",
    timeout_sec: float = 60.0,
    sv: bool | None = None,
    hierarchical: bool | None = None,
    reset_port: str | None = None,
    reset_active_low: bool = True,
) -> EquivalenceOutcome:
    """
    Formally (SAT) check whether `evolved_verilog` is logically equivalent
    to `seed_verilog` for the same module_name/port contract.

    Only meaningful when both designs share the exact same port list (which
    is guaranteed by this repo's mutation model -- mutation/crossover never
    touch the interface, only the implementation inside the module -- see
    testbench_generator.py's module docstring).
    """
    sv, hierarchical = _autodetect(seed_verilog, evolved_verilog, sv, hierarchical)
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_equiv_"))
    try:
        seed_path = workdir / ("seed.sv" if sv else "seed.v")
        evolved_path = workdir / ("evolved.sv" if sv else "evolved.v")
        seed_path.write_text(seed_verilog)
        evolved_path.write_text(evolved_verilog)

        script = (
            _build_sequential_script(module_name, seed_path, evolved_path, seq_cycles, sv, hierarchical,
                                    reset_port, reset_active_low)
            if sequential
            else _build_combinational_script(module_name, seed_path, evolved_path, sv, hierarchical)
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


def _autodetect(seed: str, evolved: str, sv, hierarchical):
    from evohdl.sandbox.design_bundle import count_modules, looks_like_systemverilog
    if sv is None:
        sv = looks_like_systemverilog(seed) or looks_like_systemverilog(evolved)
    if hierarchical is None:
        hierarchical = count_modules(seed) > 1 or count_modules(evolved) > 1
    return sv, hierarchical


def check_equivalence_equiv_make(
    seed_verilog: str,
    evolved_verilog: str,
    module_name: str = "alu_basic",
    yosys_bin: str = "yosys",
    timeout_sec: float = 60.0,
    sv: bool | None = None,
    hierarchical: bool | None = None,
) -> EquivalenceOutcome:
    """Sequential-capable equivalence via `equiv_make` / `equiv_simple` / `equiv_induct`.

    Returns equivalent=True ONLY when Yosys prints that every $equiv cell is proven. Anything else
    (unmatched register names, induction failing, timeout, tool error) is NOT equivalent-proven:
    `unproven` -> checked=True/equivalent=False/error="" (inconclusive); tool failures -> checked=False.
    """
    sv, hierarchical = _autodetect(seed_verilog, evolved_verilog, sv, hierarchical)
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_equivmake_"))
    try:
        seed_path = workdir / ("seed.sv" if sv else "seed.v")
        evolved_path = workdir / ("evolved.sv" if sv else "evolved.v")
        seed_path.write_text(seed_verilog)
        evolved_path.write_text(evolved_verilog)
        script_path = workdir / "equiv_make.ys"
        script_path.write_text(_build_equiv_make_script(module_name, seed_path, evolved_path, sv, hierarchical))
        result = run_guarded([yosys_bin, "-Q", "-T", "-s", str(script_path)],
                             timeout_sec=timeout_sec, cwd=str(workdir))
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        if not result.timed_out and EQUIV_PROVEN_RE.search(combined):
            return EquivalenceOutcome(checked=True, equivalent=True, log=combined[-2000:])
        if not result.timed_out and EQUIV_UNPROVEN_RE.search(combined):
            return EquivalenceOutcome(checked=True, equivalent=False, log=combined[-2000:])
        reason = "timeout" if result.timed_out else "yosys/equiv error"
        return EquivalenceOutcome(
            checked=False, error=f"[{reason}] {(result.stderr or result.stdout)[-1500:]}",
            log=(result.stdout or "")[-2000:],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def check_equivalence_auto(
    seed_verilog: str,
    evolved_verilog: str,
    module_name: str = "alu_basic",
    yosys_bin: str = "yosys",
    timeout_sec: float = 30.0,
    sv: bool | None = None,
    hierarchical: bool | None = None,
) -> EquivalenceOutcome:
    """What the GA loop calls: combinational -> miter+SAT proof; sequential -> equiv_make flow."""
    if is_sequential(seed_verilog) or is_sequential(evolved_verilog):
        return check_equivalence_equiv_make(seed_verilog, evolved_verilog, module_name,
                                            yosys_bin, timeout_sec, sv, hierarchical)
    return check_equivalence(seed_verilog, evolved_verilog, module_name=module_name, sequential=False,
                             yosys_bin=yosys_bin, timeout_sec=timeout_sec, sv=sv, hierarchical=hierarchical)


def selftest(yosys_bin: str = "yosys") -> int:
    """Run the checker against known-equivalent / known-different pairs with the REAL Yosys.
    This is what proves the generated scripts are valid on your machine (the unit tests only mock Yosys)."""
    import shutil as _sh
    if not _sh.which(yosys_bin):
        print(f"[selftest] '{yosys_bin}' not found on PATH"); return 2
    from evohdl.paths import SEED_DIR, DESIGNS_DIR
    alu = (SEED_DIR / "alu_basic.v").read_text()
    cnt = (SEED_DIR / "counter_4bit.v").read_text()
    alu_broken = alu.replace("a + b", "a - b", 1)
    cnt_broken = cnt.replace("count + 1'b1", "count + 2'b10", 1)
    cases = [
        ("combinational: alu == alu (expect EQUIVALENT)", lambda: check_equivalence_auto(alu, alu, "alu_basic", yosys_bin), True),
        ("combinational: alu vs broken alu (expect NOT equivalent)", lambda: check_equivalence_auto(alu, alu_broken, "alu_basic", yosys_bin), False),
        ("sequential: counter == counter via equiv_make (expect EQUIVALENT)", lambda: check_equivalence_auto(cnt, cnt, "counter_4bit", yosys_bin), True),
        ("sequential: counter vs broken counter (expect NOT proven)", lambda: check_equivalence_auto(cnt, cnt_broken, "counter_4bit", yosys_bin), False),
    ]
    hier_dir = DESIGNS_DIR / "examples" / "hier_mac"
    if hier_dir.exists():
        from evohdl.sandbox.design_bundle import load_design_bundle
        b = load_design_bundle([hier_dir / "adder8.sv", hier_dir / "mult4.sv", hier_dir / "mac_top.sv"], top="mac_top")
        broken = b.source.replace("a + b", "a ^ b", 1)
        cases += [
            ("hierarchical SV: mac_top == mac_top (expect EQUIVALENT)", lambda: check_equivalence_auto(b.source, b.source, "mac_top", yosys_bin), True),
            ("hierarchical SV: mac_top vs broken (expect NOT equivalent)", lambda: check_equivalence_auto(b.source, broken, "mac_top", yosys_bin), False),
        ]
    failures = 0
    for label, run, expect_equiv in cases:
        o = run()
        ok = (o.checked and o.equivalent) if expect_equiv else (not o.equivalent)
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {label} -> checked={o.checked} equivalent={o.equivalent} {o.error[:120]}")
    print(f"selftest: {len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys as _sys
    if "--selftest" in _sys.argv:
        raise SystemExit(selftest())
    # Smoke test: a design should always be equivalent to itself.
    demo_path = SEED_DIR / "alu_basic.v"
    if demo_path.exists():
        src = demo_path.read_text()
        outcome = check_equivalence(src, src, module_name="alu_basic")
        print(outcome)
    else:
        print("Seed design not found for smoke test.")
