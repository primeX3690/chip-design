"""
liberty.py -- parser for a practical subset of the Liberty (.lib) format + NLDM delay tables + function parsing.

Supported: library/cell/pin/timing/ff groups; area, cell_leakage_power, capacitance, direction, function,
related_pin, timing_sense, timing_type, cell_rise/cell_fall/rise_transition/fall_transition,
rise_constraint/fall_constraint (setup), lu_table_template indices (inline index_1/index_2 are used).
NOT supported: CCS/ECSM models, power tables, multi-bit cells, bus pins, `when` conditional arcs (the first arc
per related_pin is used), voltage/temperature scaling.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


class LibertyError(Exception):
    pass


# ---------------------------------------------------------------------------- generic group parser
@dataclass
class Group:
    kind: str
    args: List[str]
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List["Group"] = field(default_factory=list)


_TOK = re.compile(r'\s+|/\*.*?\*/|//[^\n]*|\\\n|("(?:[^"\\]|\\.)*")|([A-Za-z_][\w.$\[\]]*|[-+]?\d[\w.eE+-]*)|([{}();:,])', re.DOTALL)


def _tokens(text: str) -> List[str]:
    out, pos = [], 0
    while pos < len(text):
        m = _TOK.match(text, pos)
        if not m:
            raise LibertyError(f"unexpected character {text[pos]!r} at offset {pos}")
        pos = m.end()
        tok = m.group(1) or m.group(2) or m.group(3)
        if tok is not None:
            out.append(tok)
    return out


def parse_liberty_text(text: str) -> Group:
    toks = _tokens(text)
    i = 0

    def val(t: str) -> str:
        return t[1:-1] if t.startswith('"') else t

    def parse_group(kind: str) -> Group:
        nonlocal i
        # at '(' after kind
        i += 1
        args = []
        while toks[i] != ")":
            if toks[i] != ",":
                args.append(val(toks[i]))
            i += 1
        i += 1                                   # ')'
        g = Group(kind, args)
        if i < len(toks) and toks[i] == "{":
            i += 1
            while toks[i] != "}":
                parse_stmt(g)
            i += 1
        elif i < len(toks) and toks[i] == ";":
            i += 1
        return g

    def parse_stmt(parent: Group):
        nonlocal i
        name = toks[i]
        i += 1
        if toks[i] == ":":
            i += 1
            v = val(toks[i])
            i += 1
            # values like  1.0 ns  or  a b c are not expected; consume until ';'
            while toks[i] != ";":
                v += " " + val(toks[i])
                i += 1
            i += 1
            parent.attrs[name] = v
        elif toks[i] == "(":
            g = parse_group(name)
            if g.children or (i > 0 and toks[i - 1] == "}"):
                parent.children.append(g)
            else:
                # complex attribute: name (a, b, c);   e.g. index_1 ("0.1, 0.2");  values (...);
                parent.children.append(g)
        else:
            raise LibertyError(f"unexpected token {toks[i]!r} after {name!r}")

    root_kind = toks[0]
    i = 1
    root = parse_group(root_kind)
    return root


# ---------------------------------------------------------------------------- function expressions
class _FuncParser:
    def __init__(self, text: str):
        self.toks = re.findall(r"[A-Za-z_]\w*|[()!'&*|+^01]", text.replace(" ", " "))
        self.pos = 0
        self.text = text

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def eat(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def parse(self):
        e = self.or_()
        if self.pos != len(self.toks):
            raise LibertyError(f"cannot parse function '{self.text}'")
        return e

    def or_(self):
        e = self.xor()
        while self.peek() in ("|", "+"):
            self.eat()
            e = ("or", e, self.xor())
        return e

    def xor(self):
        e = self.and_()
        while self.peek() == "^":
            self.eat()
            e = ("xor", e, self.and_())
        return e

    def and_(self):
        e = self.unary()
        while self.peek() in ("&", "*") or (self.peek() is not None and self.peek() not in ("|", "+", "^", ")")):
            if self.peek() in ("&", "*"):
                self.eat()
            e = ("and", e, self.unary())
        return e

    def unary(self):
        if self.peek() == "!":
            self.eat()
            return ("not", self.unary())
        e = self.atom()
        while self.peek() == "'":
            self.eat()
            e = ("not", e)
        return e

    def atom(self):
        t = self.eat()
        if t == "(":
            e = self.or_()
            if self.eat() != ")":
                raise LibertyError(f"unbalanced parentheses in '{self.text}'")
            return e
        if t in ("0", "1"):
            return ("const", int(t))
        return ("pin", t)


def eval_function(expr, env: Dict[str, int], mask: int = 1) -> int:
    k = expr[0]
    if k == "const":
        return mask if expr[1] else 0
    if k == "pin":
        return env[expr[1]]
    if k == "not":
        return eval_function(expr[1], env, mask) ^ mask
    a, b = eval_function(expr[1], env, mask), eval_function(expr[2], env, mask)
    return a & b if k == "and" else a | b if k == "or" else a ^ b


# ---------------------------------------------------------------------------- data model
@dataclass
class Table:
    idx1: List[float]           # input slew (or constrained-pin slew)
    idx2: List[float]           # output load (or related-pin slew)
    values: List[List[float]]

    def lookup(self, x: float, y: float) -> float:
        """Bilinear interpolation (clamped extrapolation) over (idx1=x, idx2=y)."""
        def seg(axis, v):
            if len(axis) == 1:
                return 0, 0, 0.0
            if v <= axis[0]:
                return 0, 1, 0.0
            if v >= axis[-1]:
                return len(axis) - 2, len(axis) - 1, 1.0
            for k in range(len(axis) - 1):
                if axis[k] <= v <= axis[k + 1]:
                    return k, k + 1, (v - axis[k]) / (axis[k + 1] - axis[k])
            return 0, 1, 0.0
        i0, i1, tx = seg(self.idx1, x)
        j0, j1, ty = seg(self.idx2, y)
        v = self.values
        a = v[i0][j0] * (1 - ty) + v[i0][j1] * ty
        b = v[i1][j0] * (1 - ty) + v[i1][j1] * ty
        return a * (1 - tx) + b * tx


@dataclass
class TimingArc:
    related_pin: str
    sense: str = "non_unate"
    timing_type: str = "combinational"
    tables: Dict[str, Table] = field(default_factory=dict)


@dataclass
class Pin:
    name: str
    direction: str
    capacitance: float = 0.0
    function: Optional[str] = None
    expr: Optional[tuple] = None
    arcs: List[TimingArc] = field(default_factory=list)


@dataclass
class LibCell:
    name: str
    area: float
    leakage: float = 0.0
    pins: Dict[str, Pin] = field(default_factory=dict)
    is_ff: bool = False
    ff_next_state: Optional[str] = None
    ff_clocked_on: Optional[str] = None

    @property
    def input_pins(self) -> List[str]:
        return [n for n, p in self.pins.items() if p.direction == "input"]

    @property
    def output_pins(self) -> List[str]:
        return [n for n, p in self.pins.items() if p.direction == "output"]

    def truth_table(self, order: Optional[List[str]] = None) -> int:
        """Truth table of the (single) combinational output over the given input pin order."""
        order = order or self.input_pins
        out = self.pins[self.output_pins[0]]
        n = len(order)
        tt = 0
        for p in range(1 << n):
            env = {pin: (p >> i) & 1 for i, pin in enumerate(order)}
            if eval_function(out.expr, env) & 1:
                tt |= 1 << p
        return tt


@dataclass
class Library:
    name: str
    time_unit: str = "1ns"
    cap_unit: str = "1pf"
    leakage_unit: str = "1nw"
    voltage: float = 1.0
    cells: Dict[str, LibCell] = field(default_factory=dict)

    def combinational_cells(self) -> List[LibCell]:
        return [c for c in self.cells.values() if not c.is_ff and c.output_pins and c.pins[c.output_pins[0]].expr is not None]

    def ff_cells(self) -> List[LibCell]:
        return [c for c in self.cells.values() if c.is_ff]


def _floats(s: str) -> List[float]:
    return [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)]


def _table(g: Group) -> Table:
    i1 = i2 = None
    rows: List[List[float]] = []
    for ch in g.children:
        if ch.kind == "index_1":
            i1 = _floats(" ".join(ch.args))
        elif ch.kind == "index_2":
            i2 = _floats(" ".join(ch.args))
        elif ch.kind == "values":
            rows = [_floats(a) for a in ch.args]
    if i1 is None:
        i1 = [0.0]
    if i2 is None:
        i2 = [0.0]
    if len(rows) == 1 and len(i1) > 1 and len(rows[0]) == len(i1) * len(i2):
        flat = rows[0]
        rows = [flat[k * len(i2):(k + 1) * len(i2)] for k in range(len(i1))]
    if len(rows) != len(i1) or any(len(r) != len(i2) for r in rows):
        raise LibertyError("NLDM table dimensions do not match index_1 x index_2")
    return Table(i1, i2, rows)


def parse_liberty(text: str) -> Library:
    root = parse_liberty_text(text)
    if root.kind != "library":
        raise LibertyError("not a Liberty file (no top-level library group)")
    lib = Library(root.args[0] if root.args else "lib")
    lib.time_unit = root.attrs.get("time_unit", lib.time_unit).replace('"', "")
    lib.voltage = float(root.attrs.get("nom_voltage", 1.0))
    for ch in root.children:
        if ch.kind != "cell":
            continue
        cell = LibCell(ch.args[0], float(ch.attrs.get("area", 0.0)), float(ch.attrs.get("cell_leakage_power", 0.0)))
        for sub in ch.children:
            if sub.kind == "ff":
                cell.is_ff = True
                cell.ff_next_state = sub.attrs.get("next_state")
                cell.ff_clocked_on = sub.attrs.get("clocked_on")
            elif sub.kind == "pin":
                pin = Pin(sub.args[0], sub.attrs.get("direction", "input"), float(sub.attrs.get("capacitance", 0.0)))
                fn = sub.attrs.get("function")
                if fn:
                    pin.function = fn
                    pin.expr = _FuncParser(fn).parse()
                for t in sub.children:
                    if t.kind != "timing":
                        continue
                    arc = TimingArc(t.attrs.get("related_pin", "").strip('"'), t.attrs.get("timing_sense", "non_unate"),
                                    t.attrs.get("timing_type", "combinational"))
                    for tab in t.children:
                        if tab.kind in ("cell_rise", "cell_fall", "rise_transition", "fall_transition",
                                        "rise_constraint", "fall_constraint"):
                            arc.tables[tab.kind] = _table(tab)
                    pin.arcs.append(arc)
                cell.pins[pin.name] = pin
        lib.cells[cell.name] = cell
    return lib


def load_liberty(path) -> Library:
    from pathlib import Path
    return parse_liberty(Path(path).read_text())
