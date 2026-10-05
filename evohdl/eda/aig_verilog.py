"""aig_verilog.py -- write an optimized AIG back out as flat structural Verilog with the ORIGINAL module interface
(port names, order, widths), so it can replace the source module in any flow (Yosys/OpenLane/...).

Only combinational AIGs are emitted: sequential designs would need the original flop/async-reset structure preserved,
which the cycle model used by the elaborator does not guarantee (it treats reset as sampled at the clock edge)."""
from __future__ import annotations

from typing import List, Tuple

from evohdl.eda.aig import Aig
from evohdl.hdl.ast_nodes import PortDecl
from evohdl.hdl.parser import parse_source
from evohdl.hdl.pysim import Widths


def module_ports(source: str, top: str) -> List[Tuple[str, str, int]]:
    """[(direction, name, width)] in declaration order for module `top`."""
    sf = parse_source(source)
    mod = next((m for m in sf.modules if m.name == top), None)
    if mod is None:
        raise ValueError(f"module '{top}' not found")
    W = Widths(mod)
    decls = [p for p in mod.ports if isinstance(p, PortDecl)] + [it for it in mod.items if isinstance(it, PortDecl)]
    by_name = {n: pd.direction for pd in decls for n in pd.names}
    order = [p for p in mod.ports if isinstance(p, str)] or [n for pd in mod.ports if isinstance(pd, PortDecl) for n in pd.names]
    return [(by_name[n], n, W.sig[n]) for n in order]


def aig_to_verilog(aig: Aig, top: str, ports: List[Tuple[str, str, int]]) -> str:
    if aig.latches:
        raise ValueError("aig_to_verilog supports combinational designs only")
    ref = {0: "1'b0"}
    for name, lit in aig.inputs:
        ref[lit >> 1] = name

    def bitname(n: str, i: int, w: int) -> str:
        return n if w == 1 else f"{n}[{i}]"

    def lit_txt(l: int) -> str:
        if l >> 1 == 0:
            return "1'b1" if l & 1 else "1'b0"
        base = ref[l >> 1]
        return f"~{base}" if l & 1 else base

    lines = [f"module {top} ("]
    plines = []
    for d, n, w in ports:
        plines.append(f"    {d} wire" + (f" [{w - 1}:0]" if w > 1 else "") + f" {n}")
    lines.append(",\n".join(plines))
    lines.append(");")
    body = []
    for v in aig._reachable():
        if aig.kind[v] == "a":
            ref[v] = f"_n{v}"
            body.append(f"    wire _n{v} = {lit_txt(aig.f0[v])} & {lit_txt(aig.f1[v])};")
    outs = dict(aig.outputs)
    for d, n, w in ports:
        if d != "output":
            continue
        for i in range(w):
            key = bitname(n, i, w)
            body.append(f"    assign {key} = {lit_txt(outs[key])};" if key in outs else f"    assign {key} = 1'b0;")
    return "\n".join(lines + body + ["endmodule", ""])
