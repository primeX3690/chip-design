"""
techmap.py -- cut-based technology mapping of an AIG onto a Liberty library.

Algorithm (classic): enumerate <=K-input cuts per node; match each cut function against every library cell under all
input permutations and input negations (NPN-lite) and output polarity; dynamic programming over (node, phase) picks the
cheapest cover by area-flow or by arrival time; inverters bridge phases. The cover is then instantiated into a Netlist
with sharing (each (node, phase) is built once). Mapped netlists are verified in the tests by converting back to an AIG
and proving equivalence with the in-house CEC.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from evohdl.eda.aig import Aig
from evohdl.eda.liberty import LibCell, Library
from evohdl.eda.netlist import CONST0, CONST1, Netlist
from evohdl.eda.opt import cone_tt, enumerate_cuts

NOMINAL_SLEW, NOMINAL_LOAD = 0.08, 0.010


def nominal_delay(cell: LibCell) -> float:
    """Typical cell delay (ns) at a nominal slew/load, worst of rise/fall over all arcs."""
    best = 0.0
    for pin in cell.pins.values():
        for arc in pin.arcs:
            for key in ("cell_rise", "cell_fall"):
                t = arc.tables.get(key)
                if t:
                    best = max(best, t.lookup(NOMINAL_SLEW, NOMINAL_LOAD))
    return best or 0.05


@dataclass(frozen=True)
class Variant:
    cell: str
    perm: Tuple[int, ...]       # perm[j] = cut-leaf index feeding the cell's j-th input pin
    neg: Tuple[int, ...]        # neg[j] = 1 if that pin needs the leaf's complement


def _reduce(tt: int, leaves: Tuple[int, ...]) -> Tuple[int, Tuple[int, ...]]:
    """Drop leaves the function does not depend on."""
    m = len(leaves)
    nb = 1 << m

    def dep(i: int) -> bool:
        for p in range(nb):
            if ((tt >> p) & 1) != ((tt >> (p ^ (1 << i))) & 1):
                return True
        return False

    keep = [i for i in range(m) if dep(i)]
    if len(keep) == m:
        return tt, leaves
    out = 0
    for q in range(1 << len(keep)):
        p = sum(((q >> k) & 1) << keep[k] for k in range(len(keep)))
        if (tt >> p) & 1:
            out |= 1 << q
    return out, tuple(leaves[i] for i in keep)


class TechMapper:
    def __init__(self, lib: Library, objective: str = "area", k: int = 4, max_cuts: int = 8):
        if objective not in ("area", "delay"):
            raise ValueError("objective must be 'area' or 'delay'")
        self.lib, self.objective, self.k, self.max_cuts = lib, objective, k, max_cuts
        self.inv = lib.cells.get("INV")
        if self.inv is None:
            raise ValueError("library has no INV cell (needed to bridge signal phases)")
        self.inv_delay = nominal_delay(self.inv)
        self.variants: Dict[Tuple[int, int], List[Variant]] = {}
        for cell in lib.combinational_cells():
            pins = cell.input_pins
            n = len(pins)
            if n < 2 or n > k:
                continue
            f = cell.truth_table(pins)
            for perm in itertools.permutations(range(n)):
                for negmask in range(1 << n):
                    neg = tuple((negmask >> j) & 1 for j in range(n))
                    tt = 0
                    for p in range(1 << n):
                        y = 0
                        for j in range(n):
                            bit = ((p >> perm[j]) & 1) ^ neg[j]
                            y |= bit << j
                        if (f >> y) & 1:
                            tt |= 1 << p
                    self.variants.setdefault((n, tt), []).append(Variant(cell.name, perm, neg))
        self._delay = {c.name: nominal_delay(c) for c in lib.combinational_cells()}
        if not any(key[0] == 2 for key in self.variants):
            raise ValueError("library has no 2-input cells; cannot map an AIG")

    def _key(self, cost: float, arr: float):
        return (cost, arr) if self.objective == "area" else (arr, cost)

    def map(self, aig: Aig, name: str = "top", clock: str = "clk") -> Netlist:
        aig = aig.cleanup()
        lib = self.lib
        cuts = enumerate_cuts(aig, self.k, self.max_cuts)
        fan = [0] * aig.size
        for v in range(1, aig.size):
            if aig.kind[v] == "a":
                fan[aig.f0[v] >> 1] += 1
                fan[aig.f1[v] >> 1] += 1
        for l in aig._roots():
            fan[l >> 1] += 1
        INF = float("inf")
        best: Dict[Tuple[int, int], Tuple[float, float, tuple]] = {}      # (var, phase) -> (cost, arrival, choice)
        inv_a = self.inv.area

        def put(v: int, ph: int, cost: float, arr: float, choice: tuple):
            cur = best.get((v, ph))
            if cur is None or self._key(cost, arr) < self._key(cur[0], cur[1]):
                best[(v, ph)] = (cost, arr, choice)

        for v in range(1, aig.size):
            if aig.kind[v] != "a":
                best[(v, 0)] = (0.0, 0.0, ("leaf",))
                best[(v, 1)] = (inv_a, self.inv_delay, ("inv",))
                continue
            for cut in cuts[v]:
                if v in cut:
                    continue
                tt0 = cone_tt(aig, v, cut)
                tt, leaves = _reduce(tt0, cut)
                m = len(leaves)
                full = (1 << (1 << m)) - 1
                if m == 0:
                    continue
                for ph in (0, 1):
                    target = tt if ph == 0 else tt ^ full
                    if m == 1:
                        # function is the leaf itself (target==0b10) or its complement (0b01)
                        pol = 0 if target == 0b10 else 1
                        c, a, _ = best[(leaves[0], pol)]
                        put(v, ph, c, a, ("alias", leaves[0], pol))
                        continue
                    for var in self.variants.get((m, target), []):
                        cell = lib.cells[var.cell]
                        cost, arr = cell.area, 0.0
                        ok = True
                        for j in range(len(var.perm)):
                            lv, pol = leaves[var.perm[j]], var.neg[j]
                            if (lv, pol) not in best:
                                ok = False
                                break
                            c, a, _ = best[(lv, pol)]
                            cost += c / max(1, fan[lv])
                            arr = max(arr, a)
                        if ok:
                            put(v, ph, cost, arr + self._delay[var.cell], ("cell", var, leaves))
            for ph in (0, 1):                                  # inverter bridge between phases
                o = best.get((v, 1 - ph))
                if o is not None:
                    put(v, ph, o[0] + inv_a, o[1] + self.inv_delay, ("inv",))
            if (v, 0) not in best or (v, 1) not in best:
                raise ValueError(f"no library match for node {v} (library too small?)")

        nl = Netlist(name)
        nl.inputs = [n for n, _ in aig.inputs]
        nl.outputs = [n for n, _ in aig.outputs]
        net_of: Dict[Tuple[int, int], str] = {}
        for n, lit in aig.inputs:
            net_of[(lit >> 1, 0)] = n
        for l in aig.latches:
            net_of[(l["q"] >> 1, 0)] = l["name"]

        def realize(v: int, ph: int) -> str:
            if v == 0:
                return CONST1 if ph else CONST0
            key = (v, ph)
            if key in net_of:
                return net_of[key]
            choice = best[key][2]
            kind = choice[0]
            if kind == "inv" or kind == "leaf":
                src = realize(v, 1 - ph)
                out = nl.fresh_net()
                nl.add_cell("INV", {"A": src, "Y": out})
            elif kind == "alias":
                out = realize(choice[1], choice[2])
            else:
                var, leaves = choice[1], choice[2]
                cell = lib.cells[var.cell]
                pins = cell.input_pins
                conns = {pins[j]: realize(leaves[var.perm[j]], var.neg[j]) for j in range(len(pins))}
                out = nl.fresh_net()
                conns[cell.output_pins[0]] = out
                nl.add_cell(var.cell, conns)
            net_of[key] = out
            return out

        for oname, lit in aig.outputs:
            nl.aliases[oname] = realize(lit >> 1, lit & 1)
        ffs = lib.ff_cells()
        if aig.latches:
            if not ffs:
                raise ValueError("design has registers but the library has no flip-flop cell")
            ff = ffs[0]
            nl.clock = clock
            if clock not in nl.inputs:          # a Verilog `clk` port is already an (unused) AIG input
                nl.inputs.append(clock)
            for l in aig.latches:
                if l["next"] is None:
                    raise ValueError(f"register {l['name']} has no next-state function")
                d = realize(l["next"] >> 1, l["next"] & 1)
                nl.add_cell(ff.name, {"D": d, "CLK": clock, "Q": l["name"]})
        return nl


def techmap(aig: Aig, lib: Library, objective: str = "area", name: str = "top") -> Netlist:
    return TechMapper(lib, objective).map(aig, name)
