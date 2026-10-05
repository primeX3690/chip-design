"""
netlist.py -- the gate-level netlist IR: ports, nets, library-cell instances (incl. DFFs), output aliases.

Everything downstream (STA, power, Verilog writer, equivalence back to an AIG) works on this one structure instead of
text. Net names are the raw AIG names (e.g. `a[3]`); the Verilog writer sanitizes them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from evohdl.eda.aig import Aig, FALSE, TRUE
from evohdl.eda.liberty import Library, LibCell, eval_function

CONST0, CONST1 = "1'b0", "1'b1"


@dataclass
class NCell:
    name: str
    type: str
    pins: Dict[str, str]                 # pin -> net


@dataclass
class Netlist:
    name: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    cells: List[NCell] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)       # output port -> driving net
    clock: Optional[str] = None
    _n: int = 0

    def fresh_net(self) -> str:
        self._n += 1
        return f"_n{self._n}"

    def add_cell(self, ctype: str, pins: Dict[str, str]) -> NCell:
        c = NCell(f"U{len(self.cells) + 1}", ctype, pins)
        self.cells.append(c)
        return c

    def resolve(self, net: str) -> str:
        seen = set()
        while net in self.aliases and net not in seen:
            seen.add(net)
            net = self.aliases[net]
        return net

    # -------------------------------------------------------------- structure queries
    def drivers(self, lib: Library) -> Dict[str, Tuple[NCell, str]]:
        d: Dict[str, Tuple[NCell, str]] = {}
        for c in self.cells:
            for p in lib.cells[c.type].output_pins:
                d[c.pins[p]] = (c, p)
        return d

    def fanouts(self, lib: Library) -> Dict[str, List[Tuple[NCell, str]]]:
        f: Dict[str, List[Tuple[NCell, str]]] = {}
        for c in self.cells:
            for p in lib.cells[c.type].input_pins:
                f.setdefault(self.resolve(c.pins[p]), []).append((c, p))
        return f

    def topo_cells(self, lib: Library) -> List[NCell]:
        """Combinational cells in dependency order (DFFs are sequential boundaries and are listed first)."""
        drv = self.drivers(lib)
        order: List[NCell] = [c for c in self.cells if lib.cells[c.type].is_ff]
        state: Dict[str, int] = {}

        def visit(c: NCell):
            if state.get(c.name) == 2:
                return
            if state.get(c.name) == 1:
                raise ValueError(f"combinational loop through cell {c.name}")
            state[c.name] = 1
            for p in lib.cells[c.type].input_pins:
                src = drv.get(self.resolve(c.pins[p]))
                if src and not lib.cells[src[0].type].is_ff:
                    visit(src[0])
            state[c.name] = 2
            order.append(c)

        for c in self.cells:
            if not lib.cells[c.type].is_ff:
                visit(c)
        return order

    def area(self, lib: Library) -> float:
        return sum(lib.cells[c.type].area for c in self.cells)

    def cell_counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for c in self.cells:
            out[c.type] = out.get(c.type, 0) + 1
        return dict(sorted(out.items()))

    def stats(self, lib: Library) -> dict:
        return {"cells": len(self.cells), "area": round(self.area(lib), 3), "by_type": self.cell_counts(),
                "inputs": len(self.inputs), "outputs": len(self.outputs),
                "flops": sum(1 for c in self.cells if lib.cells[c.type].is_ff)}

    # -------------------------------------------------------------- simulation
    def simulate(self, lib: Library, in_vals: Dict[str, int], state: Optional[Dict[str, int]] = None, nbits: int = 1):
        """Bit-parallel simulation using the Liberty functions. Returns (outputs, next_state, net_values).
        DFF state is keyed by the DFF's Q net name."""
        mask = (1 << nbits) - 1
        val: Dict[str, int] = {CONST0: 0, CONST1: mask}
        for n in self.inputs:
            val[n] = in_vals.get(n, 0) & mask
        nxt: Dict[str, int] = {}
        for c in self.cells:
            if lib.cells[c.type].is_ff:
                q = c.pins["Q"]
                val[q] = (state or {}).get(q, 0) & mask
        for c in self.topo_cells(lib):
            lc = lib.cells[c.type]
            if lc.is_ff:
                continue
            env = {p: val[self.resolve(c.pins[p])] for p in lc.input_pins}
            val[c.pins[lc.output_pins[0]]] = eval_function(lc.pins[lc.output_pins[0]].expr, env, mask)
        for c in self.cells:
            if lib.cells[c.type].is_ff:
                nxt[c.pins["Q"]] = val[self.resolve(c.pins["D"])]
        outs = {o: val[self.resolve(self.aliases.get(o, o))] for o in self.outputs}
        return outs, nxt, val

    # -------------------------------------------------------------- back to an AIG (for equivalence checking)
    def to_aig(self, lib: Library) -> Aig:
        from evohdl.eda.opt import _build_tt
        g = Aig()
        lit: Dict[str, int] = {CONST0: FALSE, CONST1: TRUE}
        for n in self.inputs:
            lit[n] = g.new_input(n)             # the clock stays an (unused) input so interfaces match
        flops = [c for c in self.cells if lib.cells[c.type].is_ff]
        for c in flops:
            lit[c.pins["Q"]] = g.new_latch(c.pins["Q"], 0)
        for c in self.topo_cells(lib):
            lc = lib.cells[c.type]
            if lc.is_ff:
                continue
            pins = lc.input_pins
            leaves = [lit[self.resolve(c.pins[p])] for p in pins]
            lit[c.pins[lc.output_pins[0]]] = _build_tt(g, lc.truth_table(pins), len(pins), leaves)
        for o in self.outputs:
            g.add_output(o, lit[self.resolve(self.aliases.get(o, o))])
        for c in flops:
            g.set_latch_next(lit[c.pins["Q"]], lit[self.resolve(c.pins["D"])])
        return g

    # -------------------------------------------------------------- verilog
    def to_verilog(self, lib: Library) -> str:
        names: Dict[str, str] = {}
        used: set = set()

        def san(n: str) -> str:
            if n in (CONST0, CONST1):
                return n
            if n in names:
                return names[n]
            base = re.sub(r"[^A-Za-z0-9_]", "_", n)
            if not re.match(r"[A-Za-z_]", base):
                base = "n_" + base
            cand, k = base, 1
            while cand in used:
                k += 1
                cand = f"{base}_{k}"
            used.add(cand)
            names[n] = cand
            return cand

        ports = [san(n) for n in self.inputs] + [san(o) for o in self.outputs]
        lines = [f"module {re.sub(r'[^A-Za-z0-9_]', '_', self.name)} ({', '.join(ports)});"]
        lines += [f"  input {san(n)};" for n in self.inputs] + [f"  output {san(o)};" for o in self.outputs]
        nets = {c.pins[p] for c in self.cells for p in c.pins} - set(self.inputs) - {CONST0, CONST1} - set(self.outputs)
        lines += [f"  wire {san(n)};" for n in sorted(nets)]
        for c in self.cells:
            conns = ", ".join(f".{p}({san(n)})" for p, n in c.pins.items())
            lines.append(f"  {c.type} {c.name} ({conns});")
        for o in self.outputs:
            lines.append(f"  assign {san(o)} = {san(self.aliases.get(o, o))};")
        lines.append("endmodule")
        return "\n".join(lines) + "\n"
