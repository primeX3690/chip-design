"""
sat.py -- a compact CDCL SAT solver in pure Python (two watched literals, 1-UIP learning, VSIDS, phase saving,
Luby restarts, conflict limit). Independent of Yosys/minisat so equivalence checking works with no external tools.

Clauses are lists of non-zero ints (DIMACS style: +v / -v, variables 1..n).
solve() -> ("SAT", model{var: bool}) | ("UNSAT", None) | ("UNKNOWN", None)  (UNKNOWN = conflict limit hit)
It is a teaching-grade solver: fine for thousands of variables, NOT competitive with industrial solvers.
"""
from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Sequence, Tuple


def _luby(i: int) -> int:
    """i-th (0-based) element of the Luby restart sequence 1,1,2,1,1,2,4,1,1,2,..."""
    size, seq = 1, 0
    while size < i + 1:
        seq += 1
        size = 2 * size + 1
    while size - 1 != i:
        size = (size - 1) >> 1
        seq -= 1
        i = i % size
    return 1 << seq


class Solver:
    def __init__(self, nvars: int):
        self.n = nvars
        self.assign = [-1] * (nvars + 1)          # -1 unassigned, 0/1 value
        self.level = [0] * (nvars + 1)
        self.reason: List[Optional[int]] = [None] * (nvars + 1)
        self.clauses: List[List[int]] = []         # literals as codes
        self.watches: List[List[int]] = [[] for _ in range(2 * (nvars + 1))]
        self.trail: List[int] = []
        self.trail_lim: List[int] = []
        self.qhead = 0
        self.act = [0.0] * (nvars + 1)
        self.inc = 1.0
        self.phase = [0] * (nvars + 1)
        self.heap: List[Tuple[float, int]] = [(0.0, v) for v in range(1, nvars + 1)]
        heapq.heapify(self.heap)
        self.ok = True
        self.conflicts = 0

    @staticmethod
    def code(l: int) -> int:
        return 2 * abs(l) + (1 if l < 0 else 0)

    def lit_val(self, c: int) -> int:
        a = self.assign[c >> 1]
        return -1 if a == -1 else (a ^ (c & 1))

    def _enqueue(self, c: int, reason: Optional[int]) -> bool:
        v = c >> 1
        cur = self.assign[v]
        want = 1 ^ (c & 1)
        if cur != -1:
            return cur == want
        self.assign[v] = want
        self.level[v] = len(self.trail_lim)
        self.reason[v] = reason
        self.trail.append(c)
        return True

    def add_clause(self, lits: Sequence[int]) -> bool:
        if not self.ok:
            return False
        cs = sorted({self.code(l) for l in lits})
        # tautology / satisfied-at-level-0 / falsified-literal removal
        out = []
        for c in cs:
            if c ^ 1 in cs:
                return True
            val = self.lit_val(c)
            if val == 1 and self.level[c >> 1] == 0:
                return True
            if val == 0 and self.level[c >> 1] == 0:
                continue
            out.append(c)
        if not out:
            self.ok = False
            return False
        if len(out) == 1:
            if not self._enqueue(out[0], None) or self._propagate() is not None:
                self.ok = False
                return False
            return True
        self._attach(out)
        return True

    def _attach(self, cl: List[int]) -> int:
        idx = len(self.clauses)
        self.clauses.append(cl)
        self.watches[cl[0]].append(idx)
        self.watches[cl[1]].append(idx)
        return idx

    def _propagate(self) -> Optional[int]:
        while self.qhead < len(self.trail):
            p = self.trail[self.qhead]
            self.qhead += 1
            false_lit = p ^ 1
            ws = self.watches[false_lit]
            i = j = 0
            while i < len(ws):
                ci = ws[i]
                i += 1
                cl = self.clauses[ci]
                if cl[0] == false_lit:
                    cl[0], cl[1] = cl[1], cl[0]
                if self.lit_val(cl[0]) == 1:
                    ws[j] = ci
                    j += 1
                    continue
                moved = False
                for k in range(2, len(cl)):
                    if self.lit_val(cl[k]) != 0:
                        cl[1], cl[k] = cl[k], cl[1]
                        self.watches[cl[1]].append(ci)
                        moved = True
                        break
                if moved:
                    continue
                ws[j] = ci
                j += 1
                if self.lit_val(cl[0]) == 0:          # conflict
                    while i < len(ws):
                        ws[j] = ws[i]
                        i += 1
                        j += 1
                    del ws[j:]
                    self.qhead = len(self.trail)
                    return ci
                self._enqueue(cl[0], ci)
            del ws[j:]
        return None

    def _bump(self, v: int):
        self.act[v] += self.inc
        if self.act[v] > 1e100:
            for u in range(1, self.n + 1):
                self.act[u] *= 1e-100
            self.inc *= 1e-100
        heapq.heappush(self.heap, (-self.act[v], v))

    def _analyze(self, confl: int) -> Tuple[List[int], int]:
        seen = [False] * (self.n + 1)
        learnt: List[int] = [0]
        counter = 0
        p = -1
        idx = len(self.trail) - 1
        cl = self.clauses[confl]
        dl = len(self.trail_lim)
        while True:
            for c in cl:
                if p != -1 and c == p:
                    continue
                v = c >> 1
                if not seen[v] and self.level[v] > 0:
                    seen[v] = True
                    self._bump(v)
                    if self.level[v] >= dl:
                        counter += 1
                    else:
                        learnt.append(c)
            while not seen[self.trail[idx] >> 1]:
                idx -= 1
            p = self.trail[idx]
            idx -= 1
            v = p >> 1
            seen[v] = False
            counter -= 1
            if counter == 0:
                break
            cl = self.clauses[self.reason[v]]
        learnt[0] = p ^ 1
        if len(learnt) == 1:
            return learnt, 0
        bi = max(range(1, len(learnt)), key=lambda k: self.level[learnt[k] >> 1])
        learnt[1], learnt[bi] = learnt[bi], learnt[1]
        return learnt, self.level[learnt[1] >> 1]

    def _backjump(self, lvl: int):
        if len(self.trail_lim) <= lvl:
            return
        lim = self.trail_lim[lvl]
        for c in self.trail[lim:]:
            v = c >> 1
            self.phase[v] = self.assign[v]
            self.assign[v] = -1
            self.reason[v] = None
            heapq.heappush(self.heap, (-self.act[v], v))
        del self.trail[lim:]
        del self.trail_lim[lvl:]
        self.qhead = len(self.trail)

    def _decide(self) -> bool:
        while self.heap:
            _, v = heapq.heappop(self.heap)
            if self.assign[v] == -1:
                self.trail_lim.append(len(self.trail))
                self._enqueue(2 * v + (0 if self.phase[v] else 1), None)
                return True
        return False

    def solve(self, conflict_limit: int = 200000) -> str:
        if not self.ok:
            return "UNSAT"
        if self._propagate() is not None:
            return "UNSAT"
        restart_i, budget = 0, 100 * _luby(0)
        local = 0
        while True:
            confl = self._propagate()
            if confl is not None:
                self.conflicts += 1
                local += 1
                if not self.trail_lim:
                    return "UNSAT"
                learnt, back = self._analyze(confl)
                self._backjump(back)
                if len(learnt) == 1:
                    self._enqueue(learnt[0], None)
                else:
                    ci = self._attach(learnt)
                    self._enqueue(learnt[0], ci)
                self.inc /= 0.95
                if self.conflicts >= conflict_limit:
                    return "UNKNOWN"
            else:
                if local >= budget:
                    self._backjump(0)
                    restart_i += 1
                    budget, local = 100 * _luby(restart_i), 0
                if not self._decide():
                    return "SAT"

    def model(self) -> Dict[int, bool]:
        return {v: bool(self.assign[v]) for v in range(1, self.n + 1) if self.assign[v] != -1}


def solve(clauses: Sequence[Sequence[int]], nvars: int, conflict_limit: int = 200000):
    s = Solver(nvars)
    for c in clauses:
        if not s.add_clause(c):
            return "UNSAT", None
    r = s.solve(conflict_limit)
    return (r, s.model() if r == "SAT" else None)
