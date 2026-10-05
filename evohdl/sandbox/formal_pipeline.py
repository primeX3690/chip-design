"""
formal_pipeline.py -- automated formal verification of "evolved design == seed design" (gap: Yosys/eqy pipeline).

Runs every available proof method in order of strength and reports exactly WHAT was proven:

  PROVEN_UNBOUNDED   all inputs, all time: Yosys miter + SAT (combinational) or equiv_make/equiv_simple/
                     equiv_induct with every $equiv cell proven (sequential, register names matching).
  PROVEN_BY_EQY      YosysHQ eqy reported PASS (strategy + depth are printed -- read them: a `sat`/bounded
                     strategy is only as strong as its depth).
  PROVEN_BOUNDED     SAT bounded model check from reset for N clock cycles. NOT an unbounded proof.

Native fallback: if Yosys is missing, or every Yosys-based method ended inconclusive, the in-house engine
(evohdl.eda: own elaborator + CDCL SAT solver, pure Python) is tried. It needs no external tool, so a proof is
possible on a machine with nothing installed -- but it is only as trustworthy as that elaborator/solver (validated by
this repo's tests, not independently certified) and it covers the supported Verilog subset only.
  NOT_EQUIVALENT     a real counterexample (combinational, or sequential from reset).
  UNPROVEN           nothing conclusive (timeout, unmatched state encoding, tool error).
  TOOLS_MISSING      Yosys is not installed.

What "proven" does and does not mean (also written into every report):
  * Equivalence is relative to the SEED. It says nothing about the seed itself being right (that is what the
    golden-model simulation of the seed is for).
  * It is a proof about Yosys' elaboration of the two designs (x/undef handling, init values, SV subset), by
    a SAT solver you have to trust. It is not a certificate checked by an independent kernel.
  * Sequential designs whose state encoding / register names were changed cannot be matched by equiv_make and
    usually end as PROVEN_BOUNDED at best -- an honest "cannot prove" rather than a false "proved".

CLI:  python -m evohdl.sandbox.formal_pipeline --seed a.v --evolved b.v --module top [--bmc-depth 20]
      python -m evohdl.sandbox.formal_pipeline --selftest
Exit code 0 only for PROVEN_* statuses.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from evohdl.sandbox.eqy_runner import check_equivalence_eqy, eqy_available
from evohdl.sandbox.equivalence_checker import (
    EquivalenceOutcome, check_equivalence, check_equivalence_equiv_make, detect_reset_port, is_sequential,
)

PROVEN = {"PROVEN_UNBOUNDED", "PROVEN_BY_EQY", "PROVEN_BOUNDED"}

CAVEATS = [
    "Equivalence is relative to the seed design; the seed's own correctness is not proven by this check.",
    "The proof is about Yosys' elaboration of both designs and relies on the SAT/SMT solver being correct.",
    "Only designs with identical port lists are comparable (mutation never changes the interface).",
]


@dataclass
class Attempt:
    method: str
    checked: bool
    equivalent: bool
    bounded: bool
    seconds: float
    note: str = ""


@dataclass
class FormalVerdict:
    status: str
    method: str = ""
    depth: Optional[int] = None
    sequential: bool = False
    attempts: List[Attempt] = field(default_factory=list)
    caveats: List[str] = field(default_factory=lambda: list(CAVEATS))
    extra_caveats: List[str] = field(default_factory=list)

    @property
    def proven(self) -> bool:
        return self.status in PROVEN

    def to_dict(self) -> dict:
        d = asdict(self)
        d["proven"] = self.proven
        return d


def _timed(label: str, fn, attempts: List[Attempt]) -> EquivalenceOutcome:
    t0 = time.time()
    o = fn()
    note = (o.error or "")[:160] or (o.log.splitlines()[0][:160] if o.log else "")
    attempts.append(Attempt(label, o.checked, o.equivalent, o.bounded, round(time.time() - t0, 3), note))
    return o


def _counterexample(o: EquivalenceOutcome) -> bool:
    return o.checked and not o.equivalent and bool(o.error) and "counterexample" in o.error.lower()


def _native_attempt(seed_verilog: str, evolved_verilog: str, module_name: str, v: "FormalVerdict", seq: bool,
                    bmc_depth: int, timeout_sec: float):
    """In-house elaborate + CDCL equivalence. Returns a (status, method, depth) tuple when conclusive, else None."""
    t0 = time.time()
    try:
        from evohdl.eda.cec import bmc_equiv, combinational_equiv, sequential_equiv_matched
        from evohdl.eda.elaborate import elaborate
        a, b = elaborate(seed_verilog, module_name), elaborate(evolved_verilog, module_name)
    except Exception as e:  # noqa: BLE001 -- unsupported subset etc.: record and move on
        v.attempts.append(Attempt("native_elaboration", False, False, False, round(time.time() - t0, 3),
                                  f"not supported by the native engine: {str(e)[:120]}"))
        return None
    limit = max(20000, int(timeout_sec * 2000))
    caveat = ("Native engine: in-house elaborator + pure-Python CDCL solver (no Yosys). Reset is modelled as sampled at "
              "the clock edge; registers start at 0.")
    if not seq and not a.latches and not b.latches:
        r = combinational_equiv(a, b, limit)
        v.attempts.append(Attempt("native_cdcl_cec", r.status != "UNKNOWN", r.equivalent, False, round(time.time() - t0, 3), r.method + (": " + r.reason if r.reason else "")))
        if r.status == "EQUIVALENT":
            v.extra_caveats.append(caveat)
            return "PROVEN_UNBOUNDED", "native_cdcl_cec", None
        if r.status == "NOT_EQUIVALENT":
            v.extra_caveats.append(caveat + " Counterexample re-simulated on both elaborated designs.")
            return "NOT_EQUIVALENT", "native_cdcl_cec", None
        return None
    r = sequential_equiv_matched(a, b, limit)
    v.attempts.append(Attempt("native_seq_matched", r.status != "UNKNOWN", r.equivalent, False, round(time.time() - t0, 3), r.method + (": " + r.reason if r.reason else "")))
    if r.status == "EQUIVALENT":
        v.extra_caveats.append(caveat + " Registers matched by name; outputs and next-state functions proven equal for ALL states.")
        return "PROVEN_UNBOUNDED", "native_seq_matched", None
    t1 = time.time()
    bm = bmc_equiv(a, b, bmc_depth, limit)
    v.attempts.append(Attempt(f"native_bmc_{bmc_depth}", bm.status != "UNKNOWN", bm.equivalent, True, round(time.time() - t1, 3), bm.method + (": " + bm.reason if bm.reason else "")))
    if bm.status == "EQUIVALENT":
        v.extra_caveats.append(caveat + f" Only {bmc_depth} clock cycles from reset were checked (matched-state proof failed: {r.reason or r.status}).")
        return "PROVEN_BOUNDED", "native_bmc", bmc_depth
    if bm.status == "NOT_EQUIVALENT":
        v.extra_caveats.append(caveat + " Real counterexample from the reset state.")
        return "NOT_EQUIVALENT", "native_bmc", bmc_depth
    return None


def run_formal_pipeline(
    seed_verilog: str,
    evolved_verilog: str,
    module_name: str,
    yosys_bin: str = "yosys",
    eqy_bin: str = "eqy",
    timeout_sec: float = 120.0,
    bmc_depth: int = 20,
    reset_port: Optional[str] = None,
    reset_active_low: Optional[bool] = None,
    use_eqy: str = "auto",          # auto | always | never
    use_native: bool = True,        # in-house engine as fallback / when Yosys is absent
) -> FormalVerdict:
    v = FormalVerdict(status="UNPROVEN")
    seq = is_sequential(seed_verilog) or is_sequential(evolved_verilog)
    v.sequential = seq
    if not shutil.which(yosys_bin):
        v.extra_caveats.append(f"'{yosys_bin}' not found on PATH; used the native engine only.")
        res = _native_attempt(seed_verilog, evolved_verilog, module_name, v, seq, bmc_depth, timeout_sec) if use_native else None
        if res:
            v.status, v.method, v.depth = res
        else:
            v.status = "TOOLS_MISSING"
        return v
    if reset_port is None:
        found = detect_reset_port(seed_verilog)
        if found:
            reset_port, auto_low = found
            reset_active_low = auto_low if reset_active_low is None else reset_active_low
    reset_active_low = True if reset_active_low is None else reset_active_low

    def finish(status: str, method: str, depth: Optional[int] = None) -> FormalVerdict:
        v.status, v.method, v.depth = status, method, depth
        return v

    if not seq:
        o = _timed("yosys_sat_miter", lambda: check_equivalence(
            seed_verilog, evolved_verilog, module_name, sequential=False, yosys_bin=yosys_bin,
            timeout_sec=timeout_sec), v.attempts)
        if o.checked and o.equivalent:
            return finish("PROVEN_UNBOUNDED", "yosys_sat_miter")
        if _counterexample(o):
            return finish("NOT_EQUIVALENT", "yosys_sat_miter")
    else:
        o = _timed("yosys_equiv_make", lambda: check_equivalence_equiv_make(
            seed_verilog, evolved_verilog, module_name, yosys_bin=yosys_bin, timeout_sec=timeout_sec), v.attempts)
        if o.checked and o.equivalent:
            return finish("PROVEN_UNBOUNDED", "yosys_equiv_make+equiv_simple+equiv_induct")

    if use_eqy != "never" and (eqy_available(eqy_bin) or use_eqy == "always"):
        o = _timed("eqy", lambda: check_equivalence_eqy(
            seed_verilog, evolved_verilog, module_name, eqy_bin=eqy_bin, timeout_sec=max(timeout_sec, 300.0),
            depth=bmc_depth if seq else 5), v.attempts)
        if o.checked and o.equivalent:
            v.extra_caveats.append("eqy PASS: check the strategy/depth in the attempt log; a bounded strategy is "
                                   "only as strong as its depth.")
            return finish("PROVEN_BY_EQY", "eqy", o.seq_cycles or None)

    if seq:
        o = _timed(f"yosys_sat_bmc_{bmc_depth}cycles{'_from_reset' if reset_port else ''}", lambda: check_equivalence(
            seed_verilog, evolved_verilog, module_name, sequential=True, seq_cycles=bmc_depth, yosys_bin=yosys_bin,
            timeout_sec=timeout_sec, reset_port=reset_port, reset_active_low=reset_active_low), v.attempts)
        if o.checked and o.equivalent:
            v.extra_caveats.append(
                f"Only {bmc_depth} clock cycles{' from reset' if reset_port else ''} were checked; the unbounded "
                f"methods could not prove it (likely renamed/re-encoded registers).")
            return finish("PROVEN_BOUNDED", "yosys_sat_bmc", bmc_depth)
        if _counterexample(o):
            if reset_port:
                return finish("NOT_EQUIVALENT", "yosys_sat_bmc_from_reset", bmc_depth)
            v.extra_caveats.append("A counterexample was found but no reset port was detected, so it may start "
                                   "from an unreachable register state; reported as UNPROVEN, not as a bug.")
    if use_native:
        res = _native_attempt(seed_verilog, evolved_verilog, module_name, v, seq, bmc_depth, timeout_sec)
        if res:
            return finish(*res)
    return finish("UNPROVEN", "")


def render_markdown(v: FormalVerdict, module: str, seed_path: str = "", evolved_path: str = "") -> str:
    head = {
        "PROVEN_UNBOUNDED": "PROVEN EQUIVALENT (unbounded: all inputs, all time)",
        "PROVEN_BY_EQY": "PROVEN EQUIVALENT by eqy (see strategy/depth below)",
        "PROVEN_BOUNDED": f"EQUIVALENT FOR {v.depth} CLOCK CYCLES (bounded check -- NOT a full proof)",
        "NOT_EQUIVALENT": "NOT EQUIVALENT (counterexample found)",
        "UNPROVEN": "NOT PROVEN (inconclusive)",
        "TOOLS_MISSING": "NOT CHECKED (Yosys not installed)",
    }[v.status]
    lines = [f"# Formal verification: `{module}`", "", f"**{head}**", "",
             f"- seed: `{seed_path}`" if seed_path else "", f"- evolved: `{evolved_path}`" if evolved_path else "",
             f"- design type: {'sequential' if v.sequential else 'combinational'}",
             f"- deciding method: `{v.method or 'none'}`", "", "| method | ran | equivalent | bounded | seconds | note |",
             "|---|---|---|---|---|---|"]
    for a in v.attempts:
        lines.append(f"| {a.method} | {a.checked} | {a.equivalent} | {a.bounded} | {a.seconds} | {a.note.replace('|', '/')} |")
    lines += ["", "## What this does and does not show", ""] + [f"- {c}" for c in v.caveats + v.extra_caveats]
    return "\n".join(l for l in lines if l is not None) + "\n"


def write_report(v: FormalVerdict, module: str, out_dir: Path, seed_path: str = "", evolved_path: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"formal_proof_{module}.md"
    md.write_text(render_markdown(v, module, seed_path, evolved_path))
    (out_dir / f"formal_proof_{module}.json").write_text(json.dumps(v.to_dict(), indent=2))
    return md


def selftest(yosys_bin: str = "yosys") -> int:
    """Real-tool check of the whole pipeline on known pairs (equivalent / broken; combinational / sequential / FSM / multiplier)."""
    if not shutil.which(yosys_bin):
        print(f"[selftest] '{yosys_bin}' not found"); return 2
    from evohdl.paths import SEED_DIR
    rd = lambda n: (SEED_DIR / f"{n}.v").read_text()
    cases = [
        ("alu_basic == alu_basic", "alu_basic", rd("alu_basic"), rd("alu_basic"), True),
        ("alu_basic vs broken", "alu_basic", rd("alu_basic"), rd("alu_basic").replace("a + b", "a - b", 1), False),
        ("counter_4bit == itself", "counter_4bit", rd("counter_4bit"), rd("counter_4bit"), True),
        ("counter_4bit vs broken", "counter_4bit", rd("counter_4bit"), rd("counter_4bit").replace("count + 1'b1", "count + 2'b10", 1), False),
        ("fsm_seqdet == itself", "fsm_seqdet", rd("fsm_seqdet"), rd("fsm_seqdet"), True),
        ("fsm_seqdet vs broken", "fsm_seqdet", rd("fsm_seqdet"), rd("fsm_seqdet").replace("S3: next_state = din ? S4 : S2;", "S3: next_state = din ? S4 : S0;", 1), False),
        ("mult_seq8 == itself", "mult_seq8", rd("mult_seq8"), rd("mult_seq8"), True),
        ("mult_seq8 vs broken", "mult_seq8", rd("mult_seq8"), rd("mult_seq8").replace("count == 4'd7", "count == 4'd6", 1), False),
    ]
    bad = 0
    for label, mod, a, b, expect in cases:
        v = run_formal_pipeline(a, b, mod, yosys_bin=yosys_bin, bmc_depth=24, timeout_sec=120)
        ok = v.proven if expect else not v.proven
        bad += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {v.status} via {v.method or '-'}")
    print(f"formal selftest: {len(cases) - bad}/{len(cases)} as expected")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prove (or refute) that an evolved Verilog design equals its seed.")
    ap.add_argument("--seed"), ap.add_argument("--evolved"), ap.add_argument("--module")
    ap.add_argument("--yosys-bin", default="yosys"), ap.add_argument("--eqy-bin", default="eqy")
    ap.add_argument("--bmc-depth", type=int, default=20), ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--reset-port"), ap.add_argument("--reset-active-high", action="store_true")
    ap.add_argument("--use-eqy", choices=["auto", "always", "never"], default="auto")
    ap.add_argument("--out-dir", default="benchmarks")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest(a.yosys_bin)
    if not (a.seed and a.evolved and a.module):
        ap.error("--seed, --evolved and --module are required (or use --selftest)")
    v = run_formal_pipeline(Path(a.seed).read_text(), Path(a.evolved).read_text(), a.module, a.yosys_bin, a.eqy_bin,
                            a.timeout, a.bmc_depth, a.reset_port, (not a.reset_active_high) if a.reset_port else None,
                            a.use_eqy)
    md = write_report(v, a.module, Path(a.out_dir), a.seed, a.evolved)
    print(f"{v.status} ({v.method or 'no method succeeded'}) -> {md}")
    return 0 if v.proven else 1


if __name__ == "__main__":
    raise SystemExit(main())
