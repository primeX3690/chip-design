"""
aig.py -- And-Inverter Graph with structural hashing, 2-level simplification, latches and bit-parallel simulation.

Literal encoding: lit = 2*var + complement. var 0 is constant FALSE (lit 0 = 0, lit 1 = 1).
Node kinds: 'c' constant, 'i' primary input, 'l' latch output (state bit), 'a' AND.
Latches carry a next-state literal and an initial value; combinational passes treat latch outputs as inputs
and next-state literals as outputs.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

FALSE, TRUE = 0, 1


def neg(l: int) -> int:
    return l ^ 1


def var(l: int) -> int:
    return l >> 1


def is_neg(l: int) -> bool:
    return bool(l & 1)


class Aig:
    def __init__(self):
        self.kind: List[str] = ["c"]
        self.f0: List[int] = [0]
        self.f1: List[int] = [0]
        self._skey: List[Optional[Tuple[int, int]]] = [None]
        self.strash: Dict[Tuple[int, int], int] = {}
        self.inputs: List[Tuple[str, int]] = []                 # (name, lit)
        self.latches: List[dict] = []                           # {name, q, next, init}
        self.outputs: List[Tuple[str, int]] = []                # (name, lit)

    # ------------------------------------------------------------------ construction
    def _new(self, kind: str, f0: int = 0, f1: int = 0, key=None) -> int:
        self.kind.append(kind)
        self.f0.append(f0)
        self.f1.append(f1)
        self._skey.append(key)
        return (len(self.kind) - 1) * 2

    @property
    def size(self) -> int:
        return len(self.kind)

    def new_input(self, name: str) -> int:
        lit = self._new("i")
        self.inputs.append((name, lit))
        return lit

    def new_latch(self, name: str, init: int = 0) -> int:
        q = self._new("l")
        self.latches.append({"name": name, "q": q, "next": None, "init": init})
        return q

    def set_latch_next(self, q: int, nxt: int):
        for l in self.latches:
            if l["q"] == q:
                l["next"] = nxt
                return
        raise KeyError("not a latch literal")

    def add_output(self, name: str, lit: int):
        self.outputs.append((name, lit))

    def AND(self, a: int, b: int) -> int:
        if a > b:
            a, b = b, a
        if a == FALSE:
            return FALSE
        if a == TRUE:
            return b
        if a == b:
            return a
        if a == b ^ 1:
            return FALSE
        # two-level simplifications (a < b, either may be an AND node)
        for x, y in ((a, b), (b, a)):
            vx = x >> 1
            if self.kind[vx] == "a":
                p, q = self.f0[vx], self.f1[vx]
                if not (x & 1):                       # x = p & q
                    if y == p or y == q:
                        return x
                    if y == p ^ 1 or y == q ^ 1:
                        return FALSE
                else:                                 # x = !(p & q)
                    if y == p ^ 1 or y == q ^ 1:
                        return y
        key = (a, b)
        hit = self.strash.get(key)
        if hit is not None:
            return hit
        lit = self._new("a", a, b, key)
        self.strash[key] = lit
        return lit

    def OR(self, a: int, b: int) -> int:
        return self.AND(a ^ 1, b ^ 1) ^ 1

    def XOR(self, a: int, b: int) -> int:
        return self.OR(self.AND(a, b ^ 1), self.AND(a ^ 1, b))

    def XNOR(self, a: int, b: int) -> int:
        return self.XOR(a, b) ^ 1

    def MUX(self, s: int, t: int, e: int) -> int:
        if t == e:
            return t
        return self.OR(self.AND(s, t), self.AND(s ^ 1, e))

    def AND_many(self, lits: List[int]) -> int:
        lits = list(lits)
        if not lits:
            return TRUE
        while len(lits) > 1:
            nxt = [self.AND(lits[i], lits[i + 1]) for i in range(0, len(lits) - 1, 2)]
            if len(lits) % 2:
                nxt.append(lits[-1])
            lits = nxt
        return lits[0]

    def OR_many(self, lits: List[int]) -> int:
        return self.AND_many([l ^ 1 for l in lits]) ^ 1 if lits else FALSE

    # ------------------------------------------------------------------ speculative building
    def checkpoint(self) -> int:
        return len(self.kind)

    def rollback(self, mark: int):
        for v in range(len(self.kind) - 1, mark - 1, -1):
            key = self._skey[v]
            if key is not None:
                self.strash.pop(key, None)
        del self.kind[mark:], self.f0[mark:], self.f1[mark:], self._skey[mark:]

    # ------------------------------------------------------------------ analysis
    def num_ands(self, reachable_only: bool = True) -> int:
        if not reachable_only:
            return sum(1 for k in self.kind if k == "a")
        return sum(1 for v in self._reachable() if self.kind[v] == "a")

    def _roots(self) -> List[int]:
        r = [l for _, l in self.outputs]
        r += [l["next"] for l in self.latches if l["next"] is not None]
        return r

    def _reachable(self) -> List[int]:
        seen = set()
        stack = [l >> 1 for l in self._roots()]
        while stack:
            v = stack.pop()
            if v in seen or v == 0:
                continue
            seen.add(v)
            if self.kind[v] == "a":
                stack.append(self.f0[v] >> 1)
                stack.append(self.f1[v] >> 1)
        return sorted(seen)

    def levels(self) -> List[int]:
        lv = [0] * len(self.kind)
        for v in range(1, len(self.kind)):
            if self.kind[v] == "a":
                lv[v] = 1 + max(lv[self.f0[v] >> 1], lv[self.f1[v] >> 1])
        return lv

    def depth(self) -> int:
        lv = self.levels()
        roots = self._roots()
        return max((lv[l >> 1] for l in roots), default=0)

    def cleanup(self) -> "Aig":
        """Return a copy containing only logic reachable from outputs / latch next-states (inputs & latches kept)."""
        new = Aig()
        m = {0: 0}
        for name, lit in self.inputs:
            m[lit >> 1] = new.new_input(name)
        for l in self.latches:
            m[l["q"] >> 1] = new.new_latch(l["name"], l["init"])
        reach = set(self._reachable())
        for v in range(1, len(self.kind)):
            if v in reach and self.kind[v] == "a":
                a, b = self.f0[v], self.f1[v]
                m[v] = new.AND(m[a >> 1] ^ (a & 1), m[b >> 1] ^ (b & 1))
        tr = lambda l: m[l >> 1] ^ (l & 1)
        for name, lit in self.outputs:
            new.add_output(name, tr(lit))
        for l, nl in zip(self.latches, new.latches):
            nl["next"] = tr(l["next"]) if l["next"] is not None else None
        return new

    # ------------------------------------------------------------------ simulation
    def simulate(self, in_vals: Dict[str, int], state: Optional[Dict[str, int]] = None, nbits: int = 1):
        """Bit-parallel simulation: every value is an int whose low `nbits` bits are independent patterns.
        Returns (outputs: name->int, next_state: name->int, all_values: list per var)."""
        mask = (1 << nbits) - 1
        vals = [0] * len(self.kind)
        for name, lit in self.inputs:
            vals[lit >> 1] = in_vals.get(name, 0) & mask
        for l in self.latches:
            vals[l["q"] >> 1] = ((state or {}).get(l["name"], l["init"] * mask)) & mask
        lv = lambda lit: vals[lit >> 1] ^ (mask if lit & 1 else 0)
        for v in range(1, len(self.kind)):
            if self.kind[v] == "a":
                vals[v] = lv(self.f0[v]) & lv(self.f1[v])
        outs = {n: lv(l) for n, l in self.outputs}
        nxt = {l["name"]: lv(l["next"]) for l in self.latches if l["next"] is not None}
        return outs, nxt, vals

    def reset_state(self) -> Dict[str, int]:
        return {l["name"]: l["init"] for l in self.latches}

    def random_patterns(self, nbits: int, seed: int = 0) -> Dict[str, int]:
        rng = random.Random(seed)
        return {n: rng.getrandbits(nbits) for n, _ in self.inputs}

    def stats(self) -> dict:
        return {"inputs": len(self.inputs), "outputs": len(self.outputs), "latches": len(self.latches),
                "ands": self.num_ands(), "depth": self.depth()}


def import_aig(dst: Aig, src: Aig, input_map: Dict[str, int], latch_map: Optional[Dict[str, int]] = None,
               copy_outputs: bool = False):
    """Copy the logic of `src` into `dst` (structural hashing merges identical structure).
    input_map: src input name -> dst literal; latch_map: src latch name -> dst literal (else new latches).
    Returns (map var->lit, out_lits {name: lit}, next_lits {latch name: lit})."""
    m = {0: 0}
    for name, lit in src.inputs:
        m[lit >> 1] = input_map[name]
    for l in src.latches:
        m[l["q"] >> 1] = latch_map[l["name"]] if latch_map and l["name"] in latch_map else dst.new_latch(l["name"], l["init"])
    for v in range(1, len(src.kind)):
        if src.kind[v] == "a":
            a, b = src.f0[v], src.f1[v]
            m[v] = dst.AND(m[a >> 1] ^ (a & 1), m[b >> 1] ^ (b & 1))
    tr = lambda l: m[l >> 1] ^ (l & 1)
    outs = {n: tr(l) for n, l in src.outputs}
    nxt = {l["name"]: tr(l["next"]) for l in src.latches if l["next"] is not None}
    if copy_outputs:
        for n, l in outs.items():
            dst.add_output(n, l)
    return m, outs, nxt
