"""
elaborate.py -- Verilog-subset AST -> AIG (bit-blasting) with hierarchy flattening, parameters, symbolic execution of
always blocks (if / case / blocking+nonblocking) and latch (register) extraction.

Semantics mirror hdl/pysim.py exactly (unsigned, context-determined widths), and the test-suite checks that by
fuzzing random expressions and by simulating every sequential seed cycle-by-cycle against pysim.

Cycle model: every always block with an edge in its sensitivity list is one synchronous process on a single implicit
clock; the asynchronous-reset branch is modelled as a synchronous one (reset sampled at the edge), which matches the
cycle-level behaviour of the testbenches (reset is held through the clock edge). Register initial value = 0.
Unsupported (raises UnsupportedSyntax): signed arithmetic, division by non-powers of two, variable part-selects,
combinational loops, multiple clock domains semantics (they are all treated as one clock), tri-state.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from evohdl.eda.aig import Aig, FALSE, TRUE
from evohdl.hdl.ast_nodes import (
    Always, Assign, Binary, Block, Call, Case, Concat, ContAssign, Ident, If, Instance, Module, NetDecl, Nop, Num,
    ParamDecl, PortDecl, Repl, Select, SourceFile, Ternary, Unary,
)
from evohdl.hdl.lexer import UnsupportedSyntax
from evohdl.hdl.parser import parse_source
from evohdl.hdl.pysim import Widths, self_width

Bits = List[int]


# ------------------------------------------------------------------ bit-vector helpers
def ext(bits: Bits, w: int) -> Bits:
    return list(bits[:w]) + [FALSE] * max(0, w - len(bits))


def const_bits(v: int, w: int) -> Bits:
    return [TRUE if (v >> i) & 1 else FALSE for i in range(w)]


def add_bits(g: Aig, a: Bits, b: Bits, cin: int = FALSE) -> Tuple[Bits, int]:
    out, c = [], cin
    for x, y in zip(a, b):
        p = g.XOR(x, y)
        out.append(g.XOR(p, c))
        c = g.OR(g.AND(x, y), g.AND(c, p))
    return out, c


def sub_bits(g: Aig, a: Bits, b: Bits) -> Tuple[Bits, int]:
    return add_bits(g, a, [l ^ 1 for l in b], TRUE)


def mul_bits(g: Aig, a: Bits, b: Bits, w: int) -> Bits:
    acc = [FALSE] * w
    for i in range(min(w, len(b))):
        if b[i] == FALSE:
            continue
        part = [FALSE] * i + [g.AND(b[i], a[j]) for j in range(len(a))]
        acc, _ = add_bits(g, acc, ext(part, w))
    return acc


def eq_bits(g: Aig, a: Bits, b: Bits) -> int:
    return g.AND_many([g.XNOR(x, y) for x, y in zip(a, b)])


def lt_bits(g: Aig, a: Bits, b: Bits) -> int:
    return sub_bits(g, a, b)[1] ^ 1          # a < b  <=>  no carry out of a + ~b + 1


def shift_const(bits: Bits, n: int, left: bool) -> Bits:
    w = len(bits)
    if left:
        return ([FALSE] * min(n, w) + bits)[:w]
    return (bits[n:] + [FALSE] * min(n, w))[:w]


def shift_var(g: Aig, bits: Bits, amt: Bits, left: bool) -> Bits:
    w = len(bits)
    cur = list(bits)
    big = FALSE
    for k, s in enumerate(amt):
        if (1 << k) >= w:
            big = g.OR(big, s)
            continue
        sh = shift_const(cur, 1 << k, left)
        cur = [g.MUX(s, sh[i], cur[i]) for i in range(w)]
    return [g.AND(l, big ^ 1) for l in cur]


def reduce_or(g: Aig, bits: Bits) -> int:
    return g.OR_many(bits)


def mux_bits(g: Aig, s: int, a: Bits, b: Bits) -> Bits:
    return [g.MUX(s, x, y) for x, y in zip(a, b)]


# ------------------------------------------------------------------ module instance
def _walk_assigned(stmt, out: set):
    def lhs_names(l):
        if isinstance(l, Ident):
            out.add(l.name)
        elif isinstance(l, Select):
            lhs_names(l.base)
        elif isinstance(l, Concat):
            for p in l.parts:
                lhs_names(p)

    if isinstance(stmt, Assign):
        lhs_names(stmt.lhs)
    elif isinstance(stmt, Block):
        for s in stmt.stmts:
            _walk_assigned(s, out)
    elif isinstance(stmt, If):
        _walk_assigned(stmt.then, out)
        if stmt.other is not None:
            _walk_assigned(stmt.other, out)
    elif isinstance(stmt, Case):
        for it in stmt.items:
            _walk_assigned(it.body, out)


class ModInst:
    def __init__(self, el: "Elaborator", module: Module, prefix: str, overrides: Dict[str, int], top: bool):
        self.el, self.g, self.module, self.prefix = el, el.g, module, prefix
        self.W = Widths(module, overrides)
        self.env: Dict[str, Bits] = {n: [FALSE] * w for n, w in self.W.sig.items()}
        self.inputs: List[str] = []
        self.outputs: List[str] = []
        self.port_order: List[str] = []
        ports: List[PortDecl] = [p for p in module.ports if isinstance(p, PortDecl)]
        ports += [it for it in module.items if isinstance(it, PortDecl)]
        for pd in ports:
            for n in pd.names:
                (self.inputs if pd.direction == "input" else self.outputs).append(n)
        names = [p for p in module.ports if isinstance(p, str)]
        self.port_order = names or [n for pd in module.ports if isinstance(pd, PortDecl) for n in pd.names]
        self.assigns: List[ContAssign] = []
        self.comb: List[Always] = []
        self.clocked: List[Always] = []
        self.children: List[Tuple[Instance, "ModInst"]] = []
        self.reg_names: Dict[int, set] = {}
        for it in module.items:
            if isinstance(it, ContAssign):
                self.assigns.append(it)
            elif isinstance(it, NetDecl):
                for n, init in it.items:
                    if init is not None:
                        self.assigns.append(ContAssign(Ident(n), init))
            elif isinstance(it, Always):
                edged = it.sens is not None and any(e for e, _ in it.sens)
                (self.clocked if edged else self.comb).append(it)
            elif isinstance(it, Instance):
                child_mod = el.modules.get(it.module)
                if child_mod is None:
                    raise UnsupportedSyntax(f"instance of undefined module '{it.module}' (black boxes are not supported)")
                ov = self._child_overrides(it, child_mod)
                self.children.append((it, ModInst(el, child_mod, f"{prefix}{it.name}.", ov, False)))
        # top-level inputs become AIG inputs
        if top:
            for n in self.inputs:
                w = self.W.sig[n]
                self.env[n] = [self.g.new_input(self._bitname(n, i, w)) for i in range(w)]
        # registers -> latches
        self.regs: Dict[str, Bits] = {}
        for k, blk in enumerate(self.clocked):
            assigned: set = set()
            _walk_assigned(blk.body, assigned)
            self.reg_names[k] = assigned
            for n in assigned:
                if n in self.regs:
                    raise UnsupportedSyntax(f"register '{n}' is assigned in more than one clocked block")
                w = self.W.sig[n]
                q = [self.g.new_latch(self._bitname(n, i, w), 0) for i in range(w)]
                self.regs[n] = q
                self.env[n] = list(q)

    def _bitname(self, n: str, i: int, w: int) -> str:
        return f"{self.prefix}{n}" if w == 1 else f"{self.prefix}{n}[{i}]"

    def _child_overrides(self, inst: Instance, child: Module) -> Dict[str, int]:
        decl_order = [n for pd in child.header_params for n, _ in pd.items]
        decl_order += [n for it in child.items if isinstance(it, ParamDecl) and not it.local for n, _ in it.items]
        ov: Dict[str, int] = {}
        for pos, (name, e) in enumerate(inst.params):
            key = name if name is not None else (decl_order[pos] if pos < len(decl_order) else None)
            if key is None:
                raise UnsupportedSyntax("too many positional parameter overrides")
            ov[key] = self.W.const(e)
        return ov

    # -------------------------------------------------------------- expressions
    def ev(self, e, ctx: int) -> Bits:
        g = self.g
        if isinstance(e, Num):
            return const_bits(e.value or 0, ctx) if e.value is not None else [FALSE] * ctx
        if isinstance(e, Ident):
            if e.name in self.env:
                return ext(self.env[e.name], ctx)
            if e.name in self.W.params:
                return const_bits(self.W.params[e.name], ctx)
            raise UnsupportedSyntax(f"unknown identifier '{e.name}'")
        if isinstance(e, Select):
            base = self.ev(e.base, max(self_width(e.base, self.W), 1))
            if e.mode == "bit":
                try:
                    i = self.W.const(e.hi)
                    return ext([base[i] if 0 <= i < len(base) else FALSE], ctx)
                except UnsupportedSyntax:
                    idx = self.ev(e.hi, self_width(e.hi, self.W))
                    terms = [g.AND(eq_bits(g, idx, const_bits(i, len(idx))), base[i]) for i in range(len(base))
                             if i < (1 << len(idx))]
                    return ext([g.OR_many(terms)], ctx)
            if e.mode == "part":
                hi, lo = self.W.const(e.hi), self.W.const(e.lo)
                a, b = min(hi, lo), max(hi, lo)
                return ext(base[a:b + 1], ctx)
            start = self.W.const(e.hi)   # variable base of +:/-: unsupported
            width = self.W.const(e.lo)
            lo = start if e.mode == "+:" else start - width + 1
            return ext(base[max(lo, 0):max(lo, 0) + width], ctx)
        if isinstance(e, Unary):
            op = e.op
            if op in {"&", "|", "^", "~&", "~|", "~^"}:
                ob = self.ev(e.operand, self_width(e.operand, self.W))
                r = g.AND_many(ob) if op in ("&", "~&") else g.OR_many(ob) if op in ("|", "~|") else None
                if r is None:
                    r = FALSE
                    for l in ob:
                        r = g.XOR(r, l)
                if op.startswith("~"):
                    r ^= 1
                return ext([r], ctx)
            if op == "!":
                return ext([reduce_or(g, self.ev(e.operand, self_width(e.operand, self.W))) ^ 1], ctx)
            v = self.ev(e.operand, ctx)
            if op == "~":
                return [l ^ 1 for l in v]
            if op == "-":
                return sub_bits(g, [FALSE] * ctx, v)[0]
            return v
        if isinstance(e, Binary):
            return self._binary(e, ctx)
        if isinstance(e, Ternary):
            c = reduce_or(g, self.ev(e.cond, self_width(e.cond, self.W)))
            return mux_bits(g, c, self.ev(e.then, ctx), self.ev(e.other, ctx))
        if isinstance(e, Concat):
            out: Bits = []
            for p in reversed(e.parts):
                out += self.ev(p, self_width(p, self.W))
            return ext(out, ctx)
        if isinstance(e, Repl):
            unit: Bits = []
            for p in reversed(e.parts):
                unit += self.ev(p, self_width(p, self.W))
            return ext(unit * self.W.const(e.count), ctx)
        if isinstance(e, Call):
            raise UnsupportedSyntax(f"system function {e.name} is not supported by the elaborator")
        raise UnsupportedSyntax(f"cannot elaborate {type(e).__name__}")

    def _binary(self, e: Binary, ctx: int) -> Bits:
        g, op = self.g, e.op
        if op in ("&&", "||"):
            a = reduce_or(g, self.ev(e.left, self_width(e.left, self.W)))
            b = reduce_or(g, self.ev(e.right, self_width(e.right, self.W)))
            return ext([g.AND(a, b) if op == "&&" else g.OR(a, b)], ctx)
        if op in ("==", "!=", "===", "!==", "<", "<=", ">", ">="):
            cw = max(self_width(e.left, self.W), self_width(e.right, self.W))
            a, b = self.ev(e.left, cw), self.ev(e.right, cw)
            if op in ("==", "==="):
                r = eq_bits(g, a, b)
            elif op in ("!=", "!=="):
                r = eq_bits(g, a, b) ^ 1
            elif op == "<":
                r = lt_bits(g, a, b)
            elif op == ">":
                r = lt_bits(g, b, a)
            elif op == "<=":
                r = lt_bits(g, b, a) ^ 1
            else:
                r = lt_bits(g, a, b) ^ 1
            return ext([r], ctx)
        if op in ("<<", ">>", "<<<", ">>>"):
            a = self.ev(e.left, ctx)
            left = op in ("<<", "<<<")
            try:
                return shift_const(a, self.W.const(e.right), left)
            except UnsupportedSyntax:
                return shift_var(g, a, self.ev(e.right, self_width(e.right, self.W)), left)
        if op == "**":
            raise UnsupportedSyntax("power operator '**' is not supported")
        a, b = self.ev(e.left, ctx), self.ev(e.right, ctx)
        if op == "+":
            return add_bits(g, a, b)[0]
        if op == "-":
            return sub_bits(g, a, b)[0]
        if op == "*":
            return mul_bits(g, a, b, ctx)
        if op == "&":
            return [g.AND(x, y) for x, y in zip(a, b)]
        if op == "|":
            return [g.OR(x, y) for x, y in zip(a, b)]
        if op == "^":
            return [g.XOR(x, y) for x, y in zip(a, b)]
        if op in ("~^", "^~"):
            return [g.XNOR(x, y) for x, y in zip(a, b)]
        if op in ("/", "%"):
            try:
                n = self.W.const(e.right)
            except UnsupportedSyntax:
                n = 0
            if n > 0 and n & (n - 1) == 0:
                k = n.bit_length() - 1
                return shift_const(a, k, False) if op == "/" else [x if i < k else FALSE for i, x in enumerate(a)]
            raise UnsupportedSyntax("division/modulo is supported only by constant powers of two")
        raise UnsupportedSyntax(f"binary operator {op!r}")

    # -------------------------------------------------------------- statements
    def _target_width(self, lhs) -> int:
        if isinstance(lhs, Concat):
            return sum(self._target_width(p) for p in lhs.parts)
        return self_width(lhs, self.W)

    def store(self, lhs, bits: Bits, env: Dict[str, Bits]):
        g = self.g
        if isinstance(lhs, Ident):
            env[lhs.name] = ext(bits, self.W.sig[lhs.name])
        elif isinstance(lhs, Select):
            name = lhs.base.name
            cur = list(env[name])
            if lhs.mode == "bit":
                try:
                    i = self.W.const(lhs.hi)
                    if 0 <= i < len(cur):
                        cur[i] = bits[0]
                except UnsupportedSyntax:
                    idx = self.ev(lhs.hi, self_width(lhs.hi, self.W))
                    for i in range(len(cur)):
                        cur[i] = g.MUX(eq_bits(g, idx, const_bits(i, len(idx))), bits[0], cur[i])
            elif lhs.mode == "part":
                hi, lo = self.W.const(lhs.hi), self.W.const(lhs.lo)
                a, b = min(hi, lo), max(hi, lo)
                for k in range(b - a + 1):
                    cur[a + k] = bits[k] if k < len(bits) else FALSE
            else:
                raise UnsupportedSyntax("indexed part-select as assignment target")
            env[name] = cur
        elif isinstance(lhs, Concat):
            shift = 0
            for p in reversed(lhs.parts):
                pw = self._target_width(p)
                self.store(p, ext(bits[shift:shift + pw], pw), env)
                shift += pw
        else:
            raise UnsupportedSyntax("unsupported assignment target")

    def _merge(self, cond: int, e1: Dict[str, Bits], e2: Dict[str, Bits]) -> Dict[str, Bits]:
        out = dict(e1)
        for k in set(e1) | set(e2):
            a, b = e1.get(k), e2.get(k)
            if a is None or b is None or a == b:
                out[k] = a if a is not None else b
            else:
                out[k] = mux_bits(self.g, cond, a, b)
        return out

    def exec_stmt(self, st, env: Dict[str, Bits], nb: Optional[Dict[str, Bits]]):
        g = self.g
        if isinstance(st, Nop):
            return env, nb
        if isinstance(st, Assign):
            lw = self._target_width(st.lhs)
            bits = self.ev(st.rhs, max(self_width(st.rhs, self.W), lw))
            env = dict(env)
            if nb is not None:
                nb = dict(nb)
            saved = self.env
            self.env = env           # rhs of the NEXT statement must see blocking updates
            if st.blocking or nb is None:
                self.store(st.lhs, bits, env)
                if nb is not None:   # blocking assignment inside a clocked block also defines the register's next value
                    self.store(st.lhs, bits, nb)
            else:
                self.store(st.lhs, bits, nb)
            self.env = saved
            return env, nb
        if isinstance(st, Block):
            for s in st.stmts:
                saved = self.env
                self.env = env
                env, nb = self.exec_stmt(s, env, nb)
                self.env = saved
            return env, nb
        if isinstance(st, If):
            saved = self.env
            self.env = env
            c = reduce_or(g, self.ev(st.cond, self_width(st.cond, self.W)))
            e1, n1 = self.exec_stmt(st.then, dict(env), dict(nb) if nb is not None else None)
            e2, n2 = (self.exec_stmt(st.other, dict(env), dict(nb) if nb is not None else None)
                      if st.other is not None else (env, nb))
            self.env = saved
            env = self._merge(c, e1, e2)
            nb = self._merge(c, n1, n2) if nb is not None else None
            return env, nb
        if isinstance(st, Case):
            saved = self.env
            self.env = env
            cw = max([self_width(st.expr, self.W)] + [self_width(l, self.W) for it in st.items if it.labels for l in it.labels])
            sel = self.ev(st.expr, cw)
            results = []
            default = None
            for it in st.items:
                e1, n1 = self.exec_stmt(it.body, dict(env), dict(nb) if nb is not None else None)
                if it.labels is None:
                    default = (e1, n1)
                    continue
                conds = [self._label_cond(st.kind, sel, l, cw) for l in it.labels]
                results.append((self.g.OR_many(conds), e1, n1))
            self.env = saved
            cur_e, cur_n = default if default is not None else (env, nb)
            for cond, e1, n1 in reversed(results):
                cur_e = self._merge(cond, e1, cur_e)
                cur_n = self._merge(cond, n1, cur_n) if nb is not None else None
            return cur_e, cur_n
        raise UnsupportedSyntax(f"cannot elaborate statement {type(st).__name__}")

    def _label_cond(self, kind: str, sel: Bits, label, cw: int) -> int:
        g = self.g
        if kind == "case" or not (isinstance(label, Num) and label.value is None):
            return eq_bits(g, sel, self.ev(label, cw))
        text = label.text.split("'", 1)[1]
        base = {"b": 1, "o": 3, "h": 4}.get(text[0].lower())
        if base is None:
            raise UnsupportedSyntax("wildcard in decimal literal")
        digits = text[1:].replace("_", "").lower()
        conds = []
        pos = 0
        for ch in reversed(digits):
            for k in range(base):
                if ch in "xz?":
                    pos += 1
                    continue
                bit = (int(ch, 16) >> k) & 1
                if pos < len(sel):
                    conds.append(sel[pos] if bit else sel[pos] ^ 1)
                pos += 1
        for i in range(pos, len(sel)):
            conds.append(sel[i] ^ 1)          # unsized-high bits are zero
        return g.AND_many(conds)

    # -------------------------------------------------------------- rounds
    def step(self) -> bool:
        """One combinational evaluation round of this instance and its children. True if anything changed."""
        changed = False
        for a in self.assigns:
            env = dict(self.env)
            lw = self._target_width(a.lhs)
            self.store(a.lhs, self.ev(a.rhs, max(self_width(a.rhs, self.W), lw)), env)
            changed |= self._commit(env)
        for blk in self.comb:
            env, _ = self.exec_stmt(blk.body, dict(self.env), None)
            changed |= self._commit(env)
        for inst, ch in self.children:
            for pname, expr in self._connections(inst, ch):
                if expr is None:
                    continue
                if pname in ch.inputs:
                    bits = self.ev(expr, ch.W.sig[pname])
                    if ch.env[pname] != bits:
                        ch.env[pname] = bits
                        changed = True
            changed |= ch.step()
            for pname, expr in self._connections(inst, ch):
                if expr is not None and pname in ch.outputs:
                    env = dict(self.env)
                    self.store(expr, ch.env[pname], env)
                    changed |= self._commit(env)
        return changed

    def _connections(self, inst: Instance, ch: "ModInst"):
        out = []
        for pos, (name, expr) in enumerate(inst.conns):
            pname = name if name is not None else (ch.port_order[pos] if pos < len(ch.port_order) else None)
            if pname is None:
                raise UnsupportedSyntax("too many positional port connections")
            out.append((pname, expr))
        return out

    def _commit(self, env: Dict[str, Bits]) -> bool:
        changed = False
        for k, v in env.items():
            if k in self.regs:
                continue                     # latch outputs are fixed
            if self.env.get(k) != v:
                self.env[k] = v
                changed = True
        return changed

    def finish(self):
        """After convergence: next-state functions of every register (recursively)."""
        for k, blk in enumerate(self.clocked):
            names = self.reg_names[k]
            nb0 = {n: list(self.regs[n]) for n in names}
            env, nb = self.exec_stmt(blk.body, dict(self.env), nb0)
            for n in names:
                for q, nx in zip(self.regs[n], ext(nb[n], len(self.regs[n]))):
                    self.g.set_latch_next(q, nx)
        for _, ch in self.children:
            ch.finish()


class Elaborator:
    def __init__(self, sf: SourceFile):
        self.g = Aig()
        self.modules: Dict[str, Module] = {m.name: m for m in sf.modules}


def elaborate(source, top: str, overrides: Optional[Dict[str, int]] = None, max_rounds: int = 200) -> Aig:
    """Verilog text (or parsed SourceFile) -> AIG for module `top` (hierarchy flattened)."""
    sf = parse_source(source) if isinstance(source, str) else source
    el = Elaborator(sf)
    if top not in el.modules:
        raise UnsupportedSyntax(f"top module '{top}' not found (have: {sorted(el.modules)})")
    root = ModInst(el, el.modules[top], "", overrides or {}, True)
    for _ in range(max_rounds):
        if not root.step():
            break
    else:
        raise UnsupportedSyntax("combinational logic did not converge (combinational loop?)")
    root.finish()
    for n in root.outputs:
        w = root.W.sig[n]
        for i, lit in enumerate(root.env[n]):
            el.g.add_output(root._bitname(n, i, w), lit)
    return el.g
