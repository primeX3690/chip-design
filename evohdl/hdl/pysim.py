"""
pysim.py -- a tiny pure-Python evaluator/simulator for the supported Verilog subset.

Purpose: let the test-suite check REAL behaviour without Verilator/Yosys -- (1) the sequential seed
designs against their golden models, (2) that every AST mutation operator really preserves semantics
(differential simulation of original vs mutated module on random vectors).

Semantics implemented: unsigned 4-state-free (x/z -> 0) arithmetic with Verilog's context-determined
widths (operands of + - * & | ^ ~ ?: are extended to the widest of the expression and the assignment
target; comparison / reduction / logical / concat / select-index operands are self-determined).
Not implemented: signed arithmetic ($signed), hierarchy (instances), real timing. Raises
UnsupportedSyntax when it meets something it cannot model, so callers can skip rather than mis-report.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from evohdl.hdl.ast_nodes import (
    Always, Assign, Binary, Block, Call, Case, Concat, ContAssign, Ident, If, Instance, Module, NetDecl, Nop, Num,
    ParamDecl, PortDecl, Repl, Select, Ternary, Unary,
)
from evohdl.hdl.lexer import UnsupportedSyntax

_CMP = {"==", "!=", "===", "!==", "<", "<=", ">", ">="}
_LOGIC = {"&&", "||"}
_SHIFT = {"<<", ">>", "<<<", ">>>"}


def mask(w: int) -> int:
    return (1 << w) - 1


class Widths:
    """Signal widths + parameter values for one module, with self-determined width inference."""

    def __init__(self, module: Module, overrides: Optional[Dict[str, int]] = None):
        self.params: Dict[str, int] = {}
        self.sig: Dict[str, int] = {}
        self.overrides = overrides or {}
        for pd in module.header_params:
            self._params(pd)
        for p in module.ports:
            if isinstance(p, PortDecl):
                self._decl(p.width, p.names)
        for it in module.items:
            if isinstance(it, ParamDecl):
                self._params(it)
            elif isinstance(it, PortDecl):
                self._decl(it.width, it.names)
            elif isinstance(it, NetDecl):
                self._decl(it.width, [n for n, _ in it.items], integer=it.kind == "integer")

    def _params(self, pd: ParamDecl):
        for name, e in pd.items:
            # instance overrides apply to `parameter` (not `localparam`) declarations
            self.params[name] = self.overrides[name] if (name in self.overrides and not pd.local) else self.const(e)

    def _decl(self, rng, names, integer: bool = False):
        w = 32 if integer else 1
        if rng:
            w = abs(self.const(rng[0]) - self.const(rng[1])) + 1
        for n in names:
            self.sig[n] = w

    def const(self, e) -> int:
        if isinstance(e, Num):
            if e.value is None:
                raise UnsupportedSyntax("x/z literal in constant expression")
            return e.value & mask(e.width) if e.width else e.value   # sized literals truncate to their width
        if isinstance(e, Ident):
            if e.name in self.params:
                return self.params[e.name]
            raise UnsupportedSyntax(f"non-constant identifier {e.name!r} where a constant is required")
        if isinstance(e, (Binary, Unary)):
            self._require_constant(e)
            return int(evaluate(e, {}, self, self_width(e, self), consts=self.params))
        raise UnsupportedSyntax(f"unsupported constant expression {type(e).__name__}")

    def _require_constant(self, e):
        """Reject expressions that mention signals: they must NOT be silently evaluated with signals = 0."""
        if isinstance(e, Num):
            return
        if isinstance(e, Ident):
            if e.name not in self.params:
                raise UnsupportedSyntax(f"non-constant identifier {e.name!r} where a constant is required")
            return
        if isinstance(e, Binary):
            self._require_constant(e.left)
            self._require_constant(e.right)
        elif isinstance(e, Unary):
            self._require_constant(e.operand)
        else:
            raise UnsupportedSyntax(f"non-constant expression {type(e).__name__} where a constant is required")


def self_width(e, W: Widths) -> int:
    if isinstance(e, Num):
        return e.width if e.width is not None else 32
    if isinstance(e, Ident):
        if e.name in W.sig:
            return W.sig[e.name]
        if e.name in W.params:
            return 32
        raise UnsupportedSyntax(f"unknown identifier {e.name!r}")
    if isinstance(e, Select):
        if e.mode == "bit":
            return 1
        if e.mode == "part":
            return abs(W.const(e.hi) - W.const(e.lo)) + 1
        return W.const(e.lo)
    if isinstance(e, Unary):
        return 1 if e.op in {"!", "&", "|", "^", "~&", "~|", "~^"} else self_width(e.operand, W)
    if isinstance(e, Binary):
        if e.op in _CMP or e.op in _LOGIC:
            return 1
        if e.op in _SHIFT or e.op == "**":
            return self_width(e.left, W)
        return max(self_width(e.left, W), self_width(e.right, W))
    if isinstance(e, Ternary):
        return max(self_width(e.then, W), self_width(e.other, W))
    if isinstance(e, Concat):
        return sum(self_width(p, W) for p in e.parts)
    if isinstance(e, Repl):
        return W.const(e.count) * sum(self_width(p, W) for p in e.parts)
    raise UnsupportedSyntax(f"cannot size {type(e).__name__}")


def evaluate(e, env: Dict[str, int], W: Widths, ctx: int, consts: Optional[Dict[str, int]] = None) -> int:
    """Value of `e` evaluated in a context of `ctx` bits (result masked to ctx)."""
    m = mask(ctx)
    if isinstance(e, Num):
        if e.value is None:
            return 0
        return e.value & m
    if isinstance(e, Ident):
        if e.name in W.params and e.name not in env:
            return W.params[e.name] & m
        return env.get(e.name, 0) & m
    if isinstance(e, Select):
        base = evaluate(e.base, env, W, max(self_width(e.base, W), 1))
        if e.mode == "bit":
            idx = evaluate(e.hi, env, W, self_width(e.hi, W))
            return ((base >> idx) & 1) & m
        if e.mode == "part":
            hi, lo = W.const(e.hi), W.const(e.lo)
            lo_, hi_ = min(hi, lo), max(hi, lo)
            return ((base >> lo_) & mask(hi_ - lo_ + 1)) & m
        start = evaluate(e.hi, env, W, self_width(e.hi, W))
        width = W.const(e.lo)
        lo_ = start if e.mode == "+:" else start - width + 1
        return ((base >> max(lo_, 0)) & mask(width)) & m
    if isinstance(e, Unary):
        op = e.op
        if op in {"&", "|", "^", "~&", "~|", "~^"}:
            ow = self_width(e.operand, W)
            v = evaluate(e.operand, env, W, ow)
            if op in ("&", "~&"):
                r = int(v == mask(ow))
            elif op in ("|", "~|"):
                r = int(v != 0)
            else:
                r = bin(v).count("1") & 1
            if op.startswith("~"):
                r ^= 1
            return r & m
        if op == "!":
            return int(evaluate(e.operand, env, W, self_width(e.operand, W)) == 0) & m
        v = evaluate(e.operand, env, W, ctx)
        if op == "~":
            return (~v) & m
        if op == "-":
            return (-v) & m
        return v & m  # unary +
    if isinstance(e, Binary):
        op = e.op
        if op in _LOGIC:
            a = evaluate(e.left, env, W, self_width(e.left, W)) != 0
            b = evaluate(e.right, env, W, self_width(e.right, W)) != 0
            return int(a and b if op == "&&" else a or b) & m
        if op in _CMP:
            cw = max(self_width(e.left, W), self_width(e.right, W))
            a, b = evaluate(e.left, env, W, cw), evaluate(e.right, env, W, cw)
            r = {"==": a == b, "===": a == b, "!=": a != b, "!==": a != b,
                 "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
            return int(r) & m
        if op in _SHIFT:
            a = evaluate(e.left, env, W, ctx)
            sh = evaluate(e.right, env, W, self_width(e.right, W))
            return ((a << sh) if op in ("<<", "<<<") else (a >> sh)) & m
        a, b = evaluate(e.left, env, W, ctx), evaluate(e.right, env, W, ctx)
        if op == "+":
            return (a + b) & m
        if op == "-":
            return (a - b) & m
        if op == "*":
            return (a * b) & m
        if op == "&":
            return a & b
        if op == "|":
            return a | b
        if op == "^":
            return a ^ b
        if op in ("~^", "^~"):
            return (~(a ^ b)) & m
        if op == "/":
            return (a // b) & m if b else 0
        if op == "%":
            return (a % b) & m if b else 0
        if op == "**":
            return (a ** evaluate(e.right, env, W, self_width(e.right, W))) & m
        raise UnsupportedSyntax(f"binary operator {op!r}")
    if isinstance(e, Ternary):
        c = evaluate(e.cond, env, W, self_width(e.cond, W)) != 0
        return evaluate(e.then if c else e.other, env, W, ctx)
    if isinstance(e, Concat):
        v = 0
        for p in e.parts:
            pw = self_width(p, W)
            v = (v << pw) | evaluate(p, env, W, pw)
        return v & m
    if isinstance(e, Repl):
        n = W.const(e.count)
        unit = 0
        uw = 0
        for p in e.parts:
            pw = self_width(p, W)
            unit = (unit << pw) | evaluate(p, env, W, pw)
            uw += pw
        v = 0
        for _ in range(n):
            v = (v << uw) | unit
        return v & m
    raise UnsupportedSyntax(f"cannot evaluate {type(e).__name__}")


class PySim:
    """Cycle simulator for a single (non-hierarchical) module."""

    def __init__(self, module: Module):
        self.m = module
        self.W = Widths(module)
        self.env: Dict[str, int] = {n: 0 for n in self.W.sig}
        self.assigns: List[ContAssign] = []
        self.comb: List[Always] = []
        self.clocked: List[Always] = []
        for it in module.items:
            if isinstance(it, Instance):
                raise UnsupportedSyntax("hierarchy (module instances) is not supported by pysim")
            if isinstance(it, ContAssign):
                self.assigns.append(it)
            elif isinstance(it, NetDecl):
                for name, init in it.items:
                    if init is not None:
                        self.assigns.append(ContAssign(Ident(name), init))
            elif isinstance(it, Always):
                edged = it.sens is not None and any(edge for edge, _ in it.sens)
                (self.clocked if edged else self.comb).append(it)
        self.settle()

    # -- assignment helpers
    def _lhs_width(self, lhs) -> int:
        return self._target_width(lhs)

    def _target_width(self, lhs) -> int:
        if isinstance(lhs, Concat):
            return sum(self._target_width(p) for p in lhs.parts)
        return self_width(lhs, self.W)

    def _store(self, lhs, value: int, sink: Dict[str, int], reads: Dict[str, int]):
        if isinstance(lhs, Ident):
            sink[lhs.name] = value & mask(self.W.sig[lhs.name])
        elif isinstance(lhs, Select):
            name = lhs.base.name
            cur = sink.get(name, reads.get(name, 0))
            if lhs.mode == "bit":
                i = evaluate(lhs.hi, reads, self.W, self_width(lhs.hi, self.W))
                cur = (cur & ~(1 << i)) | ((value & 1) << i)
            elif lhs.mode == "part":
                hi, lo = self.W.const(lhs.hi), self.W.const(lhs.lo)
                lo_, hi_ = min(hi, lo), max(hi, lo)
                mk = mask(hi_ - lo_ + 1) << lo_
                cur = (cur & ~mk) | ((value << lo_) & mk)
            else:
                raise UnsupportedSyntax("indexed part-select as assignment target")
            sink[name] = cur & mask(self.W.sig[name])
        elif isinstance(lhs, Concat):
            shift = 0
            for p in reversed(lhs.parts):
                pw = self._target_width(p)
                self._store(p, (value >> shift) & mask(pw), sink, reads)
                shift += pw
        else:
            raise UnsupportedSyntax("unsupported assignment target")

    def _rhs(self, rhs, lhs) -> int:
        lw = self._target_width(lhs)
        ctx = max(self_width(rhs, self.W), lw)
        return evaluate(rhs, self.env, self.W, ctx)

    def _exec(self, st, nb: Dict[str, int]):
        if isinstance(st, Nop):
            return
        if isinstance(st, Assign):
            v = self._rhs(st.rhs, st.lhs)
            if st.blocking:
                self._store(st.lhs, v, self.env, self.env)
            else:
                self._store(st.lhs, v, nb, self.env)
        elif isinstance(st, Block):
            for s in st.stmts:
                self._exec(s, nb)
        elif isinstance(st, If):
            c = evaluate(st.cond, self.env, self.W, self_width(st.cond, self.W)) != 0
            if c:
                self._exec(st.then, nb)
            elif st.other is not None:
                self._exec(st.other, nb)
        elif isinstance(st, Case):
            cw = max([self_width(st.expr, self.W)] + [self_width(l, self.W) for it in st.items if it.labels for l in it.labels])
            sel = evaluate(st.expr, self.env, self.W, cw)
            default = None
            for it in st.items:
                if it.labels is None:
                    default = it
                    continue
                if any(self._label_match(st.kind, sel, l, cw) for l in it.labels):
                    self._exec(it.body, nb)
                    return
            if default is not None:
                self._exec(default.body, nb)
        else:
            raise UnsupportedSyntax(f"cannot execute {type(st).__name__}")

    def _label_match(self, kind: str, sel: int, label, cw: int) -> bool:
        if kind == "case" or not (isinstance(label, Num) and label.value is None):
            return evaluate(label, self.env, self.W, cw) == sel
        # casez/casex with wildcard bits in a literal: x/z/? positions are don't-care
        text = label.text.split("'", 1)[1][1:].replace("_", "").lower()
        base = {"b": 1, "o": 3, "h": 4}.get(label.text.split("'", 1)[1][0].lower(), None)
        if base is None:
            raise UnsupportedSyntax("wildcard in decimal literal")
        care = val = 0
        for ch in text:
            care = (care << base) | (0 if ch in "xz?" else mask(base))
            val = (val << base) | (0 if ch in "xz?" else int(ch, 16))
        return (sel & care) == (val & care)

    # -- simulation
    def settle(self, limit: int = 64):
        for _ in range(limit):
            before = dict(self.env)
            for a in self.assigns:
                self._store(a.lhs, self._rhs(a.rhs, a.lhs), self.env, self.env)
            for blk in self.comb:
                self._exec(blk.body, {})
            if self.env == before:
                return
        raise UnsupportedSyntax("combinational logic did not settle (loop?)")

    def _fire(self, blocks: List[Always]):
        nb: Dict[str, int] = {}
        for blk in blocks:
            self._exec(blk.body, nb)
        self.env.update(nb)

    def cycle(self, inputs: Dict[str, int], clk: str = "clk") -> Dict[str, int]:
        """Apply `inputs`, fire async-edge blocks for any 1->0 transition of an async signal, then one posedge
        of `clk`. Returns a copy of all signal values after the edge."""
        prev = dict(self.env)
        for k, v in inputs.items():
            self.env[k] = v & mask(self.W.sig[k])
        self.settle()
        neg = [b for b in self.clocked
               if any(edge == "negedge" and getattr(s, "name", None) in inputs
                      and prev.get(s.name, 0) == 1 and self.env[s.name] == 0 for edge, s in b.sens)]
        if neg:
            self._fire(neg)
            self.settle()
        pos = [b for b in self.clocked if any(edge == "posedge" and s.name == clk for edge, s in b.sens)]
        self._fire(pos)
        self.settle()
        return dict(self.env)

    def comb_eval(self, inputs: Dict[str, int]) -> Dict[str, int]:
        for k, v in inputs.items():
            self.env[k] = v & mask(self.W.sig[k])
        self.settle()
        return dict(self.env)
