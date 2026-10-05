"""AST -> Verilog text. Nested binary/ternary expressions are fully parenthesized, so printing can never
change operator precedence. Simple single-assignment case branches stay on ONE line (`label: x = y;`),
which the legacy line-based operators (crossover, operator_swap) rely on."""
from __future__ import annotations

from typing import List

from evohdl.hdl.ast_nodes import (
    Always, Assign, Binary, Block, Call, Case, CaseItem, Concat, ContAssign, Ident, If, Instance, Module, NetDecl,
    Nop, Num, ParamDecl, PortDecl, Repl, Select, SourceFile, Ternary, Unary,
)

IND = "    "


def pe(e, top: bool = True) -> str:
    """Print an expression. `top` False => wrap compound expressions in parentheses."""
    if isinstance(e, Num):
        return e.text
    if isinstance(e, Ident):
        return e.name
    if isinstance(e, Select):
        base = pe(e.base, False)
        if e.mode == "bit":
            return f"{base}[{pe(e.hi)}]"
        sep = {"part": ":", "+:": "+:", "-:": "-:"}[e.mode]
        return f"{base}[{pe(e.hi)}{sep}{pe(e.lo)}]"
    if isinstance(e, Unary):
        return f"{e.op}{pe(e.operand, False)}"
    if isinstance(e, Binary):
        s = f"{pe(e.left, False)} {e.op} {pe(e.right, False)}"
        return s if top else f"({s})"
    if isinstance(e, Ternary):
        s = f"{pe(e.cond, False)} ? {pe(e.then, False)} : {pe(e.other, False)}"
        return s if top else f"({s})"
    if isinstance(e, Concat):
        return "{" + ", ".join(pe(p) for p in e.parts) + "}"
    if isinstance(e, Repl):
        return "{" + pe(e.count, False) + "{" + ", ".join(pe(p) for p in e.parts) + "}}"
    if isinstance(e, Call):
        return f"{e.name}(" + ", ".join(pe(a) for a in e.args) + ")"
    raise TypeError(f"cannot print {type(e).__name__}")


def _simple(stmt) -> bool:
    return isinstance(stmt, Assign) or isinstance(stmt, Nop)


def _assign_text(a: Assign) -> str:
    return f"{pe(a.lhs)} {'=' if a.blocking else '<='} {pe(a.rhs)};"


def ps(stmt, depth: int) -> List[str]:
    pad = IND * depth
    if isinstance(stmt, Nop):
        return [pad + ";"]
    if isinstance(stmt, Assign):
        return [pad + _assign_text(stmt)]
    if isinstance(stmt, Block):
        out = [pad + "begin"]
        for s in stmt.stmts:
            out += ps(s, depth + 1)
        return out + [pad + "end"]
    if isinstance(stmt, If):
        out = [pad + f"if ({pe(stmt.cond)})"]
        out += ps(stmt.then, depth + 1) if not isinstance(stmt.then, Block) else ps(stmt.then, depth)
        if stmt.other is not None:
            out.append(pad + "else")
            nested = isinstance(stmt.other, If)
            out += ps(stmt.other, depth) if (isinstance(stmt.other, Block) or nested) else ps(stmt.other, depth + 1)
        return out
    if isinstance(stmt, Case):
        out = [pad + f"{stmt.kind} ({pe(stmt.expr)})"]
        for it in stmt.items:
            label = "default" if it.labels is None else ", ".join(pe(l) for l in it.labels)
            body = it.body
            if isinstance(body, Assign):
                out.append(pad + IND + f"{label}: {_assign_text(body)}")
            elif isinstance(body, Nop):
                out.append(pad + IND + f"{label}: ;")
            else:
                inner = ps(body, depth + 1) if isinstance(body, Block) else ps(Block([body]), depth + 1)
                inner[0] = pad + IND + f"{label}: " + inner[0].lstrip()
                out += inner
        return out + [pad + "endcase"]
    raise TypeError(f"cannot print {type(stmt).__name__}")


def _rng(w) -> str:
    return f" [{pe(w[0])}:{pe(w[1])}]" if w else ""


def _port(p: PortDecl) -> str:
    return f"{p.direction}" + (f" {p.kind}" if p.kind else "") + (" signed" if p.signed else "") + _rng(p.width) + " " + ", ".join(p.names)


def pitem(it, depth: int = 1) -> List[str]:
    pad = IND * depth
    if isinstance(it, PortDecl):
        return [pad + _port(it) + ";"]
    if isinstance(it, NetDecl):
        decl = []
        for name, init in it.items:
            decl.append(name if init is None else f"{name} = {pe(init)}")
        return [pad + it.kind + (" signed" if it.signed else "") + _rng(it.width) + " " + ", ".join(decl) + ";"]
    if isinstance(it, ParamDecl):
        kw = "localparam" if it.local else "parameter"
        body = ", ".join(f"{n} = {pe(v)}" for n, v in it.items)
        return [pad + f"{kw}{_rng(it.width)} {body};"]
    if isinstance(it, ContAssign):
        return [pad + f"assign {pe(it.lhs)} = {pe(it.rhs)};"]
    if isinstance(it, Always):
        if it.sens is None:
            head = "@(*)" if it.kind != "always_comb" else ""
        else:
            head = "@(" + " or ".join((f"{e} " if e else "") + pe(s) for e, s in it.sens) + ")"
        line = pad + it.kind + (" " + head if head else "")
        body = ps(it.body, depth) if isinstance(it.body, Block) else ps(it.body, depth + 1)
        if isinstance(it.body, Block):
            body[0] = line + " " + body[0].lstrip()
            return body
        return [line] + body
    if isinstance(it, Instance):
        params = ""
        if it.params:
            params = " #(" + ", ".join((f".{n}({pe(v)})" if n else pe(v)) for n, v in it.params) + ")"
        conns = ", ".join((f".{n}({pe(v) if v is not None else ''})" if n else pe(v)) for n, v in it.conns)
        return [pad + f"{it.module}{params} {it.name} ({conns});"]
    raise TypeError(f"cannot print {type(it).__name__}")


def print_module(m: Module) -> str:
    head = f"module {m.name}"
    if m.header_params:
        ps_ = []
        for pd in m.header_params:
            for n, v in pd.items:
                ps_.append(f"parameter{_rng(pd.width)} {n} = {pe(v)}")
        head += " #(" + ", ".join(ps_) + ")"
    lines: List[str] = []
    if m.ports and all(isinstance(p, PortDecl) for p in m.ports):
        lines.append(head + " (")
        lines.append(",\n".join(IND + _port(p) for p in m.ports))
        lines.append(");")
    elif m.ports:
        lines.append(head + " (" + ", ".join(str(p) for p in m.ports) + ");")
    else:
        lines.append(head + ";")
    for it in m.items:
        lines += pitem(it)
    lines.append("endmodule")
    return "\n".join(lines)


def print_source(sf: SourceFile) -> str:
    return "\n\n".join(print_module(m) for m in sf.modules) + "\n"
