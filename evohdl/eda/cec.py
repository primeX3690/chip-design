"""
cec.py -- equivalence checking on AIGs with the in-house SAT solver (no Yosys).

  combinational_equiv(a, b)   miter over outputs; structural hashing first (often proves it with no SAT at all)
  sequential_equiv_matched    same latch names/inits: compare outputs AND next-state functions (induction-style,
                              sound only when state encodings match -- the analogue of Yosys equiv_make)
  bmc_equiv(a, b, k)          unroll k frames from the reset state and compare outputs (bounded, NOT a full proof)

Results are CecResult(status, ...) with status in EQUIVALENT | NOT_EQUIVALENT | UNKNOWN. A NOT_EQUIVALENT answer
always carries a counterexample that has been RE-SIMULATED on both AIGs before being reported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from evohdl.eda.aig import Aig, FALSE, TRUE, import_aig
from evohdl.eda.sat import Solver


@dataclass
class CecResult:
    status: str                                   # EQUIVALENT | NOT_EQUIVALENT | UNKNOWN
    method: str = ""
    reason: str = ""
    counterexample: Dict[str, int] = field(default_factory=dict)
    frames: int = 0
    sat_calls: int = 0
    conflicts: int = 0

    @property
    def equivalent(self) -> bool:
        return self.status == "EQUIVALENT"


def aig_to_cnf(aig: Aig, roots: List[int]):
    """Tseitin CNF of the cones of `roots` (literals). Returns (clauses, var_of_aig_var dict, nvars)."""
    var_of: Dict[int, int] = {}
    clauses: List[List[int]] = []
    order: List[int] = []
    seen = set()
    stack = [r >> 1 for r in roots]
    while stack:
        v = stack.pop()
        if v in seen:
            continue
        seen.add(v)
        order.append(v)
        if aig.kind[v] == "a":
            stack += [aig.f0[v] >> 1, aig.f1[v] >> 1]
    n = 0
    for v in sorted(seen):
        n += 1
        var_of[v] = n
    lit = lambda l: (var_of[l >> 1] * (-1 if l & 1 else 1))
    for v in sorted(seen):
        if v == 0:
            clauses.append([-var_of[0]])               # constant false
        elif aig.kind[v] == "a":
            o, a, b = var_of[v], lit(aig.f0[v]), lit(aig.f1[v])
            clauses += [[-o, a], [-o, b], [o, -a, -b]]
    return clauses, var_of, n, lit


def _solve_miter(aig: Aig, diff_lits: List[int], conflict_limit: int):
    """Is any of diff_lits satisfiable (=1)? Returns (status, assignment by aig var or None, conflicts)."""
    roots = [d for d in diff_lits if d != FALSE]
    if not roots:
        return "UNSAT", None, 0
    if any(d == TRUE for d in roots):
        return "SAT", {}, 0
    clauses, var_of, n, lit = aig_to_cnf(aig, roots)
    s = Solver(n)
    for c in clauses:
        s.add_clause(c)
    s.add_clause([lit(d) for d in roots])               # at least one difference
    r = s.solve(conflict_limit)
    if r == "SAT":
        model = s.model()
        return "SAT", {v: model.get(var_of[v], False) for v in var_of}, s.conflicts
    return r, None, s.conflicts


def _same_interface(a: Aig, b: Aig) -> Optional[str]:
    if sorted(n for n, _ in a.inputs) != sorted(n for n, _ in b.inputs):
        return "input names differ"
    if sorted(n for n, _ in a.outputs) != sorted(n for n, _ in b.outputs):
        return "output names differ"
    return None


def combinational_equiv(a: Aig, b: Aig, conflict_limit: int = 200000, verify_cex: bool = True) -> CecResult:
    if a.latches or b.latches:
        return CecResult("UNKNOWN", "comb", "design has latches: use sequential_equiv_matched or bmc_equiv")
    bad = _same_interface(a, b)
    if bad:
        return CecResult("UNKNOWN", "comb", bad)
    m = Aig()
    ins = {name: m.new_input(name) for name, _ in a.inputs}
    _, oa, _ = import_aig(m, a, ins)
    _, ob, _ = import_aig(m, b, ins)
    diffs = []
    for name in oa:
        if oa[name] != ob[name]:
            diffs.append(m.XOR(oa[name], ob[name]))
    if not diffs or all(d == FALSE for d in diffs):
        return CecResult("EQUIVALENT", "structural-hash", "all outputs hash to identical literals")
    status, asg, confl = _solve_miter(m, diffs, conflict_limit)
    if status == "UNSAT":
        return CecResult("EQUIVALENT", "sat-miter", sat_calls=1, conflicts=confl)
    if status == "SAT":
        cex = {name: int(asg.get(lit >> 1, False)) ^ (lit & 1) if (lit >> 1) in asg else 0 for name, lit in m.inputs}
        if verify_cex:
            ra, _, _ = a.simulate(cex)
            rb, _, _ = b.simulate(cex)
            if all(ra[k] == rb[k] for k in ra):
                return CecResult("UNKNOWN", "sat-miter", "internal error: SAT model did not reproduce a difference")
        return CecResult("NOT_EQUIVALENT", "sat-miter", counterexample=cex, sat_calls=1, conflicts=confl)
    return CecResult("UNKNOWN", "sat-miter", f"conflict limit {conflict_limit} reached", sat_calls=1, conflicts=confl)


def _latch_view(a: Aig, b: Aig) -> Optional[str]:
    la = {l["name"]: l["init"] for l in a.latches}
    lb = {l["name"]: l["init"] for l in b.latches}
    if la.keys() != lb.keys():
        return "latch (register) names differ: state encodings cannot be matched"
    if la != lb:
        return "latch initial values differ"
    return None


def sequential_equiv_matched(a: Aig, b: Aig, conflict_limit: int = 200000) -> CecResult:
    """Outputs and next-state functions equal as functions of (inputs, shared latch outputs).

    Sound for equivalence from ANY state, hence from reset: if every output and every register's next-state function
    agree for all (input, state) pairs, the designs behave identically on all input sequences. Incomplete: designs
    that differ only on unreachable states are reported NOT_EQUIVALENT (with a counterexample state)."""
    bad = _same_interface(a, b) or _latch_view(a, b)
    if bad:
        return CecResult("UNKNOWN", "seq-matched", bad)
    m = Aig()
    ins = {name: m.new_input(name) for name, _ in a.inputs}
    qs = {l["name"]: m.new_latch(l["name"], l["init"]) for l in a.latches}
    _, oa, na = import_aig(m, a, ins, qs)
    _, ob, nb = import_aig(m, b, ins, qs)
    diffs = [m.XOR(oa[k], ob[k]) for k in oa if oa[k] != ob[k]]
    diffs += [m.XOR(na[k], nb[k]) for k in na if na[k] != nb[k]]
    if not diffs:
        return CecResult("EQUIVALENT", "seq-matched/structural-hash")
    status, asg, confl = _solve_miter(m, diffs, conflict_limit)
    if status == "UNSAT":
        return CecResult("EQUIVALENT", "seq-matched/sat", sat_calls=1, conflicts=confl)
    if status == "SAT":
        cex = {name: int(asg.get(lit >> 1, False)) for name, lit in m.inputs}
        cex.update({l["name"]: int(asg.get(l["q"] >> 1, False)) for l in m.latches})
        return CecResult("NOT_EQUIVALENT", "seq-matched/sat", "difference found from an arbitrary state (may be unreachable)",
                         counterexample=cex, sat_calls=1, conflicts=confl)
    return CecResult("UNKNOWN", "seq-matched/sat", "conflict limit reached", conflicts=confl)


def bmc_equiv(a: Aig, b: Aig, k: int = 12, conflict_limit: int = 200000) -> CecResult:
    """Bounded check: both designs start in their reset state; compare outputs over k clock cycles for all inputs."""
    bad = _same_interface(a, b)
    if bad:
        return CecResult("UNKNOWN", "bmc", bad)
    m = Aig()
    state_a = {l["name"]: (TRUE if l["init"] else FALSE) for l in a.latches}
    state_b = {l["name"]: (TRUE if l["init"] else FALSE) for l in b.latches}
    diffs: List[int] = []
    frame_inputs: List[Dict[str, int]] = []
    for f in range(k):
        ins = {name: m.new_input(f"{name}@{f}") for name, _ in a.inputs}
        frame_inputs.append(ins)
        _, oa, na = import_aig(m, a, ins, state_a)
        _, ob, nb = import_aig(m, b, ins, state_b)
        diffs += [m.XOR(oa[n], ob[n]) for n in oa if oa[n] != ob[n]]
        state_a, state_b = na, nb
        # latches absent from next maps (never assigned) hold their literal
        for l in a.latches:
            state_a.setdefault(l["name"], state_a.get(l["name"], FALSE))
        for l in b.latches:
            state_b.setdefault(l["name"], state_b.get(l["name"], FALSE))
    if not diffs:
        return CecResult("EQUIVALENT", f"bmc-{k}", "bounded: identical output literals in every frame", frames=k)
    status, asg, confl = _solve_miter(m, diffs, conflict_limit)
    if status == "UNSAT":
        return CecResult("EQUIVALENT", f"bmc-{k}", f"bounded to {k} cycles from reset (NOT a full proof)", frames=k,
                         sat_calls=1, conflicts=confl)
    if status == "SAT":
        trace = {f"{name}@{f}": int(asg.get(frame_inputs[f][name] >> 1, False)) for f in range(k) for name in frame_inputs[f]}
        return CecResult("NOT_EQUIVALENT", f"bmc-{k}", "real counterexample from reset", counterexample=trace, frames=k,
                         sat_calls=1, conflicts=confl)
    return CecResult("UNKNOWN", f"bmc-{k}", "conflict limit reached", frames=k, conflicts=confl)
