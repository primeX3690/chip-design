"""
opt.py -- AIG optimization: cut-based rewriting (functional hashing with Shannon resynthesis), tree balancing and
SAT-based functional reduction (fraig-lite). Every pass returns a NEW functionally-equivalent AIG; the test-suite
proves that with the in-house CEC on every benchmark, and optimize() additionally refuses to return a result that is
larger than its input.

rewrite : for each node enumerate <=4-input cuts, resynthesize each cut function by Shannon decomposition into the new
          graph, and keep whichever implementation adds the fewest NEW nodes (structural hashing makes identical
          sub-functions share). Never trusts a heuristic gain: the baseline copy is always a candidate.
balance : re-associate AND trees by level (depth reduction, area-neutral).
fraig   : random-simulation signatures + SAT proof (cec.py) to merge functionally equivalent nodes.
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

from evohdl.eda.aig import Aig, FALSE, TRUE
from evohdl.eda.sat import Solver
from evohdl.eda.cec import aig_to_cnf

K_CUT = 4


# ---------------------------------------------------------------------------- helpers
def _copy_interface(old: Aig, new: Aig) -> Dict[int, int]:
    m = {0: 0}
    for name, lit in old.inputs:
        m[lit >> 1] = new.new_input(name)
    for l in old.latches:
        m[l["q"] >> 1] = new.new_latch(l["name"], l["init"])
    return m


def _finish(old: Aig, new: Aig, m: Dict[int, int]) -> Aig:
    tr = lambda l: m[l >> 1] ^ (l & 1)
    for name, lit in old.outputs:
        new.add_output(name, tr(lit))
    for lo, ln in zip(old.latches, new.latches):
        ln["next"] = tr(lo["next"]) if lo["next"] is not None else None
    return new.cleanup()


# ---------------------------------------------------------------------------- cuts + truth tables
def enumerate_cuts(aig: Aig, k: int = K_CUT, max_cuts: int = 8) -> Dict[int, List[Tuple[int, ...]]]:
    cuts: Dict[int, List[Tuple[int, ...]]] = {0: [()]}
    for v in range(1, aig.size):
        if aig.kind[v] != "a":
            cuts[v] = [(v,)]
            continue
        a, b = aig.f0[v] >> 1, aig.f1[v] >> 1
        found = {(v,)}
        for ca in cuts[a]:
            for cb in cuts[b]:
                u = tuple(sorted(set(ca) | set(cb)))
                if len(u) <= k:
                    found.add(u)
        lst = sorted(found, key=lambda c: (len(c), c))
        keep: List[Tuple[int, ...]] = []
        for c in lst:                                   # drop dominated (superset) cuts
            if not any(set(o) <= set(c) for o in keep if o != c):
                keep.append(c)
        cuts[v] = keep[:max_cuts]
    return cuts


def cone_tt(aig: Aig, v: int, leaves: Tuple[int, ...]) -> int:
    m = len(leaves)
    nb = 1 << m
    full = (1 << nb) - 1
    memo: Dict[int, int] = {0: 0}
    for i, lv in enumerate(leaves):
        pat = 0
        for p in range(nb):
            if (p >> i) & 1:
                pat |= 1 << p
        memo[lv] = pat

    def go(x: int) -> int:
        if x in memo:
            return memo[x]
        a, b = aig.f0[x], aig.f1[x]
        va = go(a >> 1) ^ (full if a & 1 else 0)
        vb = go(b >> 1) ^ (full if b & 1 else 0)
        memo[x] = va & vb
        return memo[x]

    return go(v)


def _cofactor(tt: int, m: int, i: int, val: int) -> int:
    nb = 1 << m
    out = 0
    for p in range(nb):
        q = (p | (1 << i)) if val else (p & ~(1 << i))
        if (tt >> q) & 1:
            out |= 1 << p
    return out


def _build_tt(g: Aig, tt: int, m: int, leaves: List[int], top: int = -1) -> int:
    nb = 1 << m
    full = (1 << nb) - 1
    if tt == 0:
        return FALSE
    if tt == full:
        return TRUE
    support = [i for i in range(m) if _cofactor(tt, m, i, 0) != _cofactor(tt, m, i, 1)]
    i = top if top in support else support[0]
    f0, f1 = _cofactor(tt, m, i, 0), _cofactor(tt, m, i, 1)
    x = leaves[i]
    if f1 == (f0 ^ full):
        return g.XOR(x, _build_tt(g, f0, m, leaves))
    if f0 == 0:
        return g.AND(x, _build_tt(g, f1, m, leaves))
    if f1 == 0:
        return g.AND(x ^ 1, _build_tt(g, f0, m, leaves))
    if f0 == full:
        return g.OR(x ^ 1, _build_tt(g, f1, m, leaves))
    if f1 == full:
        return g.OR(x, _build_tt(g, f0, m, leaves))
    return g.MUX(x, _build_tt(g, f1, m, leaves), _build_tt(g, f0, m, leaves))


def _best_build(g: Aig, tt: int, m: int, leaves: List[int]) -> Tuple[int, int]:
    """Try each support variable as the top split; return (cost_in_new_nodes, top_var) of the cheapest."""
    full = (1 << (1 << m)) - 1
    if tt in (0, full):
        return 0, -1
    support = [i for i in range(m) if _cofactor(tt, m, i, 0) != _cofactor(tt, m, i, 1)]
    best = (10 ** 9, support[0])
    for top in support:
        mark = g.checkpoint()
        _build_tt(g, tt, m, leaves, top)
        cost = g.checkpoint() - mark
        g.rollback(mark)
        if cost < best[0]:
            best = (cost, top)
    return best


# ---------------------------------------------------------------------------- passes
def rewrite(old: Aig, k: int = K_CUT, max_cuts: int = 8) -> Aig:
    new = Aig()
    m = _copy_interface(old, new)
    cuts = enumerate_cuts(old, k, max_cuts)
    for v in range(1, old.size):
        if old.kind[v] != "a":
            continue
        a, b = old.f0[v], old.f1[v]
        la, lb = m[a >> 1] ^ (a & 1), m[b >> 1] ^ (b & 1)
        mark = new.checkpoint()
        new.AND(la, lb)
        best_cost, best = new.checkpoint() - mark, None
        new.rollback(mark)
        for cut in cuts[v]:
            if len(cut) < 2 or v in cut:
                continue
            tt = cone_tt(old, v, cut)
            leaves = [m[x] for x in cut]
            cost, top = _best_build(new, tt, len(cut), leaves)
            if cost < best_cost:
                best_cost, best = cost, (tt, cut, leaves, top)
        if best is None:
            m[v] = new.AND(la, lb)
        else:
            tt, cut, leaves, top = best
            m[v] = _build_tt(new, tt, len(cut), leaves, top)
    return _finish(old, new, m)


def balance(old: Aig) -> Aig:
    fan = [0] * old.size
    for v in range(1, old.size):
        if old.kind[v] == "a":
            fan[old.f0[v] >> 1] += 1
            fan[old.f1[v] >> 1] += 1
    for l in old._roots():
        fan[l >> 1] += 1
    new = Aig()
    m = _copy_interface(old, new)
    lv: Dict[int, int] = {}

    def level(lit: int) -> int:
        v = lit >> 1
        if v >= len(lv_arr):
            lv_arr.extend([0] * (new.size - len(lv_arr) + 8))
        return lv_arr[v]

    lv_arr: List[int] = [0] * 64

    def new_and(x: int, y: int) -> int:
        r = new.AND(x, y)
        if r >> 1 >= len(lv_arr):
            lv_arr.extend([0] * (new.size - len(lv_arr) + 8))
        if new.kind[r >> 1] == "a":
            lv_arr[r >> 1] = 1 + max(level(x), level(y))
        return r

    def collect(lit: int, out: List[int], root: bool):
        v = lit >> 1
        if not (lit & 1) and old.kind[v] == "a" and (root or fan[v] == 1):
            collect(old.f0[v], out, False)
            collect(old.f1[v], out, False)
        else:
            out.append(lit)

    for v in range(1, old.size):
        if old.kind[v] != "a":
            continue
        leaves: List[int] = []
        collect(v << 1, leaves, True)
        mapped = [m[x >> 1] ^ (x & 1) for x in leaves]
        mapped = sorted(set(mapped), key=lambda l: level(l))
        if any((l ^ 1) in mapped for l in mapped):
            m[v] = FALSE
            continue
        while len(mapped) > 1:
            a, b = mapped[0], mapped[1]
            r = new_and(a, b)
            mapped = sorted(mapped[2:] + [r], key=lambda l: level(l))
        m[v] = mapped[0] if mapped else TRUE
    return _finish(old, new, m)


def fraig(old: Aig, nsim: int = 256, conflict_limit: int = 400, max_checks: int = 4000, seed: int = 1) -> Aig:
    """Merge functionally equivalent (up to complement) nodes proven by SAT."""
    rng = random.Random(seed)
    work = Aig.cleanup(old)                    # private copy we may extend/rollback
    mask = (1 << nsim) - 1
    ins = {n: rng.getrandbits(nsim) for n, _ in work.inputs}
    st = {l["name"]: rng.getrandbits(nsim) for l in work.latches}
    _, _, vals = work.simulate(ins, st, nsim)
    reps: Dict[int, List[int]] = {}
    repl: Dict[int, int] = {}                  # var -> literal it is equivalent to (lower var)
    checks = 0
    for v in range(1, work.size):
        if work.kind[v] != "a":
            if work.kind[v] in "il":
                reps.setdefault(vals[v] if not (vals[v] & 1) else vals[v] ^ mask, []).append(v << 1)
            continue
        sig = vals[v]
        key = sig if not (sig & 1) else sig ^ mask
        cands = reps.setdefault(key, [])
        if key == 0 and not any(c == 0 for c in cands):
            cands.append(FALSE)                                  # constant class
        merged = False
        for rl in cands:
            if checks >= max_checks:
                break
            rv = rl >> 1
            phase = (vals[v] != (vals[rv] ^ (mask if rl & 1 else 0))) if rv else (vals[v] != 0)
            target = (rl ^ 1) if (rv and phase) else (rl if rv else (TRUE if phase else FALSE))
            mark = work.checkpoint()
            d = work.XOR(v << 1, repl_lit(target, repl))
            ok = False
            if d == FALSE:
                ok = True
            elif d != TRUE:
                clauses, var_of, n, lit = aig_to_cnf(work, [d])
                s = Solver(n)
                for c in clauses:
                    s.add_clause(c)
                s.add_clause([lit(d)])
                checks += 1
                ok = s.solve(conflict_limit) == "UNSAT"
            work.rollback(mark)
            if ok:
                repl[v] = repl_lit(target, repl)
                merged = True
                break
        if not merged:
            cands.append(v << 1)
    new = Aig()
    m = _copy_interface(work, new)
    for v in range(1, work.size):
        if work.kind[v] == "a":
            if v in repl:
                r = repl[v]
                m[v] = m[r >> 1] ^ (r & 1)
            else:
                a, b = work.f0[v], work.f1[v]
                m[v] = new.AND(m[a >> 1] ^ (a & 1), m[b >> 1] ^ (b & 1))
    return _finish(work, new, m)


def repl_lit(lit: int, repl: Dict[int, int]) -> int:
    while (lit >> 1) in repl:
        r = repl[lit >> 1]
        lit = r ^ (lit & 1)
    return lit


def optimize(aig: Aig, effort: int = 2, rounds: int = 3, log=None) -> Aig:
    """effort 1: rewrite+balance; 2: + fraig (SAT sweeping). Never returns a larger graph than the input."""
    best = aig.cleanup()
    cur = best
    for r in range(rounds):
        prev = (cur.num_ands(), cur.depth())
        passes = [("rewrite", rewrite), ("balance", balance)] + ([("fraig", fraig)] if effort >= 2 else [])
        for name, fn in passes:
            cur = fn(cur)
            if log:
                log(f"round {r + 1} {name}: ands={cur.num_ands()} depth={cur.depth()}")
        if (cur.num_ands(), cur.depth()) < (best.num_ands(), best.depth()):
            best = cur
        if (cur.num_ands(), cur.depth()) >= prev:
            break
    return best
