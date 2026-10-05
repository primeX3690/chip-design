"""
ast_nodes.py -- a small Verilog-2001 / SystemVerilog-subset syntax tree.

Pure-Python dataclasses (structural equality), so `parse(print(parse(src))) == parse(src)` is a real
round-trip check and mutation operators can be tested without any EDA tool.

Supported subset (everything else raises hdl.parser.UnsupportedSyntax and callers fall back to
their text-level behaviour): modules with ANSI or non-ANSI ports, parameters/localparams, wire/reg/
logic declarations, continuous assigns, always / always_comb / always_ff / always_latch, begin/end,
if/else, case/casez/casex, blocking and non-blocking assignments, the full expression grammar
(including ?:, concatenation, replication, selects, reductions) and module instantiation.
NOT supported: generate, functions/tasks, initial, for/while loops, interfaces, packages, structs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

# ------------------------------------------------------------------ expressions


@dataclass
class Num:
    text: str                       # original literal text, printed verbatim
    width: Optional[int] = None     # None for unsized
    value: Optional[int] = None     # None if the literal contains x/z/?


@dataclass
class Ident:
    name: str


@dataclass
class Select:
    base: "Expr"
    hi: "Expr"
    lo: Optional["Expr"] = None     # None => single-bit select
    mode: str = "bit"               # "bit" | "part" | "+:" | "-:"


@dataclass
class Unary:
    op: str                         # ~ ! - + & | ^ ~& ~| ~^
    operand: "Expr"


@dataclass
class Binary:
    op: str
    left: "Expr"
    right: "Expr"


@dataclass
class Ternary:
    cond: "Expr"
    then: "Expr"
    other: "Expr"


@dataclass
class Concat:
    parts: List["Expr"]


@dataclass
class Repl:
    count: "Expr"
    parts: List["Expr"]


@dataclass
class Call:
    name: str                       # e.g. $signed
    args: List["Expr"]


Expr = Union[Num, Ident, Select, Unary, Binary, Ternary, Concat, Repl, Call]
EXPR_TYPES = (Num, Ident, Select, Unary, Binary, Ternary, Concat, Repl, Call)

# ------------------------------------------------------------------ statements


@dataclass
class Assign:
    lhs: Expr
    rhs: Expr
    blocking: bool = True


@dataclass
class Block:
    stmts: List["Stmt"] = field(default_factory=list)


@dataclass
class If:
    cond: Expr
    then: "Stmt"
    other: Optional["Stmt"] = None


@dataclass
class CaseItem:
    labels: Optional[List[Expr]]    # None => default
    body: "Stmt"


@dataclass
class Case:
    kind: str                       # case | casez | casex
    expr: Expr
    items: List[CaseItem] = field(default_factory=list)


@dataclass
class Nop:
    pass


Stmt = Union[Assign, Block, If, Case, Nop]

# ------------------------------------------------------------------ module items

Range = Tuple[Expr, Expr]           # (msb, lsb)


@dataclass
class PortDecl:
    direction: str                  # input | output | inout
    kind: Optional[str]             # wire | reg | logic | None
    signed: bool
    width: Optional[Range]
    names: List[str]


@dataclass
class NetDecl:
    kind: str                       # wire | reg | logic | integer
    signed: bool
    width: Optional[Range]
    items: List[Tuple[str, Optional[Expr]]]   # (name, optional initializer / continuous assign)


@dataclass
class ParamDecl:
    local: bool
    width: Optional[Range]
    items: List[Tuple[str, Expr]]


@dataclass
class ContAssign:
    lhs: Expr
    rhs: Expr


@dataclass
class Always:
    kind: str                       # always | always_comb | always_ff | always_latch
    sens: Optional[List[Tuple[Optional[str], Expr]]]   # None => @(*) ; (edge|None, signal)
    body: Stmt


@dataclass
class Instance:
    module: str
    params: List[Tuple[Optional[str], Expr]]
    name: str
    conns: List[Tuple[Optional[str], Optional[Expr]]]


Item = Union[PortDecl, NetDecl, ParamDecl, ContAssign, Always, Instance]


@dataclass
class Module:
    name: str
    header_params: List[ParamDecl] = field(default_factory=list)
    ports: List[Union[str, PortDecl]] = field(default_factory=list)  # PortDecl => ANSI header, str => non-ANSI
    items: List[Item] = field(default_factory=list)


@dataclass
class SourceFile:
    modules: List[Module] = field(default_factory=list)
