"""
ast_operators.py -- structure-aware mutation operators built on the real syntax tree (gap F).

Unlike the regex operators, these rewrite ANY sub-expression (not just `x = a OP b` lines), keep the
file syntactically valid by construction (the printer parenthesizes everything), and are semantics-
preserving identities: commutativity, associativity, De Morgan, distributivity/factoring,
subtract-as-add, ternary inversion, double-negation / idempotence removal, if/else <-> ternary,
case-branch reordering (only when labels are provably distinct constants) and common-subexpression
extraction of bitwise logic over side-effect-free operands.

They are verified two ways: (1) tests/unit/test_ast_operators.py differentially SIMULATES original vs
mutated modules in pure Python (hdl/pysim.py); (2) in a real run the fitness gate (formal equivalence
or Verilator) still decides acceptance.

If the source is outside the supported subset (hdl.parser.ParseError) each operator falls back to its
older regex counterpart where one exists, otherwise it is a no-op.
"""
from __future__ import annotations

import copy
import random
from dataclasses import fields, is_dataclass
from typing import Callable, List, Optional, Tuple

from evohdl.evolutionary_engine.algebraic_rewrites import (
    Mutation, mutate_commutative_swap, mutate_demorgan, mutate_sub_as_add as _regex_sub_as_add,
    mutate_ternary_invert as _regex_ternary_invert,
)
from evohdl.hdl.ast_nodes import (
    Always, Assign, Binary, Block, Case, CaseItem, ContAssign, EXPR_TYPES, Ident, If, Instance, Module, NetDecl,
    Num, ParamDecl, PortDecl, Select, SourceFile, Ternary, Unary,
)
from evohdl.hdl.lexer import UnsupportedSyntax
from evohdl.hdl.parser import ParseError, parse_source
from evohdl.hdl.printer import pe, print_source
from evohdl.hdl.pysim import Widths, self_width

# Fields never rewritten: assignment targets, declaration widths, sensitivity lists, instance wiring.
_SKIP = {"lhs", "width", "sens", "header_params", "params", "conns", "ports"}


# --------------------------------------------------------------------------- generic tree rewriting
def _walk(obj, state: dict, match: Callable, rewrite: Callable):
    """Pre-order traversal. The `state["target"]`-th matching node is replaced by rewrite(node).
    With target == -1 nothing is replaced and state["n"] ends up as the number of matches."""
    if is_dataclass(obj) and not isinstance(obj, type):
        if match(obj):
            if state["n"] == state["target"]:
                state["n"] += 1
                return rewrite(obj)
            state["n"] += 1
        for f in fields(obj):
            if f.name in _SKIP:
                continue
            setattr(obj, f.name, _walk(getattr(obj, f.name), state, match, rewrite))
        return obj
    if isinstance(obj, list):
        return [_walk(x, state, match, rewrite) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_walk(x, state, match, rewrite) for x in obj)
    return obj


def _count(root, match) -> int:
    st = {"n": 0, "target": -1}
    _walk(copy.deepcopy(root), st, match, lambda x: x)
    return st["n"]


def _replace_nth(root, match, rewrite, n: int):
    st = {"n": 0, "target": n}
    return _walk(root, st, match, rewrite)


def _noop(kind: str, why: str, source: str) -> Tuple[str, Mutation]:
    return source, Mutation(kind, f"no-op: {why}")


def _parse(source: str) -> Optional[SourceFile]:
    try:
        return parse_source(source)
    except ParseError:
        return None


# --------------------------------------------------------------------------- expression rewrites
COMMUTATIVE = {"+", "*", "&", "|", "^", "~^", "==", "!=", "&&", "||"}
ASSOCIATIVE = {"+", "*", "&", "|", "^"}


def _m_comm(e):
    return isinstance(e, Binary) and e.op in COMMUTATIVE and e.left != e.right


def _r_comm(e):
    return Binary(e.op, e.right, e.left)


def _m_assoc(e):
    return isinstance(e, Binary) and e.op in ASSOCIATIVE and (
        (isinstance(e.left, Binary) and e.left.op == e.op) or (isinstance(e.right, Binary) and e.right.op == e.op))


def _r_assoc(e):
    if isinstance(e.left, Binary) and e.left.op == e.op:       # (a o b) o c -> a o (b o c)
        return Binary(e.op, e.left.left, Binary(e.op, e.left.right, e.right))
    return Binary(e.op, Binary(e.op, e.left, e.right.left), e.right.right)   # a o (b o c) -> (a o b) o c


_FLIP = {"&": "|", "|": "&"}


def _m_demorgan(e):
    return (isinstance(e, Unary) and e.op == "~" and isinstance(e.operand, Binary) and e.operand.op in _FLIP) or (
        isinstance(e, Binary) and e.op in _FLIP and isinstance(e.left, Unary) and e.left.op == "~"
        and isinstance(e.right, Unary) and e.right.op == "~")


def _r_demorgan(e):
    if isinstance(e, Unary):                                    # ~(a & b) -> ~a | ~b
        b = e.operand
        return Binary(_FLIP[b.op], Unary("~", b.left), Unary("~", b.right))
    return Unary("~", Binary(_FLIP[e.op], e.left.operand, e.right.operand))   # ~a | ~b -> ~(a & b)


def _distribute(e):
    """a&(b|c) -> (a&b)|(a&c); a|(b&c) -> (a|b)&(a|c); and the factoring inverses. None if n/a."""
    if not isinstance(e, Binary) or e.op not in _FLIP:
        return None
    inner = _FLIP[e.op]
    if isinstance(e.right, Binary) and e.right.op == inner:                       # distribute
        return Binary(inner, Binary(e.op, e.left, e.right.left), Binary(e.op, e.left, e.right.right))
    if (isinstance(e.left, Binary) and e.left.op == inner and isinstance(e.right, Binary) and e.right.op == inner
            and e.left.left == e.right.left):                                       # factor: (a o b) i (a o c)
        return None
    # factor form: top op is `e.op`, children use the dual op sharing a left operand
    if (isinstance(e.left, Binary) and isinstance(e.right, Binary) and e.left.op == inner and e.right.op == inner
            and e.left.left == e.right.left):
        return Binary(inner, e.left.left, Binary(e.op, e.left.right, e.right.right))
    return None


def _factor(e):
    # (a & b) | (a & c) -> a & (b | c);   (a | b) & (a | c) -> a | (b & c)
    if (isinstance(e, Binary) and e.op in _FLIP and isinstance(e.left, Binary) and isinstance(e.right, Binary)
            and e.left.op == _FLIP[e.op] and e.right.op == _FLIP[e.op] and e.left.left == e.right.left):
        return Binary(_FLIP[e.op], e.left.left, Binary(e.op, e.left.right, e.right.right))
    return None


def _m_dist(e):
    return _distribute(e) is not None or _factor(e) is not None


def _r_dist(e):
    return _distribute(e) or _factor(e)


def _m_sub(e):
    return isinstance(e, Binary) and e.op == "-"


def _r_sub(e):
    return Binary("+", Binary("+", e.left, Unary("~", e.right)), Num("1'b1", 1, 1))


def _m_tern(e):
    return isinstance(e, Ternary)


def _r_tern(e):
    return Ternary(Unary("!", e.cond), e.other, e.then)


def _m_simplify(e):
    return (isinstance(e, Unary) and e.op == "~" and isinstance(e.operand, Unary) and e.operand.op == "~") or (
        isinstance(e, Binary) and e.op in ("&", "|") and e.left == e.right)


def _r_simplify(e):
    return e.operand.operand if isinstance(e, Unary) else e.left


# --------------------------------------------------------------------------- statement rewrites
def _single_assign(s):
    if isinstance(s, Block) and len(s.stmts) == 1:
        s = s.stmts[0]
    return s if isinstance(s, Assign) else None


def _if_to_tern(s):
    if not isinstance(s, If) or s.other is None:
        return None
    a, b = _single_assign(s.then), _single_assign(s.other)
    if a and b and a.lhs == b.lhs and a.blocking == b.blocking:
        return Assign(a.lhs, Ternary(s.cond, a.rhs, b.rhs), a.blocking)
    return None


def _tern_to_if(s):
    if isinstance(s, Assign) and isinstance(s.rhs, Ternary):
        t = s.rhs
        return If(t.cond, Assign(s.lhs, t.then, s.blocking), Assign(s.lhs, t.other, s.blocking))
    return None


def _m_ifter(n):
    return _if_to_tern(n) is not None or _tern_to_if(n) is not None


def _r_ifter(n):
    return _if_to_tern(n) or _tern_to_if(n)


# --------------------------------------------------------------------------- operator factories
def _make_op(kind: str, match: Callable, rewrite: Callable, regex_fallback=None):
    def op(source: str, rng: random.Random) -> Tuple[str, Mutation]:
        sf = _parse(source)
        if sf is None:
            if regex_fallback is not None:
                out, info = regex_fallback(source, rng)
                return out, Mutation(kind, f"{info.description} (regex fallback: source outside AST subset)")
            return _noop(kind, "source outside the supported Verilog subset", source)
        n = _count(sf, match)
        if n == 0:
            return _noop(kind, "no matching construct", source)
        k = rng.randrange(n)
        before = pe_node_text(sf, match, k)
        new_sf = _replace_nth(sf, match, rewrite, k)
        return print_source(new_sf), Mutation(kind, f"rewrote #{k + 1}/{n}: {before}")
    op.__name__ = f"mutate_{kind}"
    return op


def pe_node_text(sf: SourceFile, match: Callable, k: int) -> str:
    """Human-readable text of the k-th matching node (for mutation_history)."""
    found: List[str] = []

    def m(x):
        ok = match(x)
        if ok:
            found.append(pe(x) if isinstance(x, EXPR_TYPES) else type(x).__name__)
        return False
    _walk(copy.deepcopy(sf), {"n": 0, "target": -1}, m, lambda x: x)
    return found[k] if k < len(found) else "?"


mutate_ast_commutative = _make_op("ast_commutative", _m_comm, _r_comm, mutate_commutative_swap)
mutate_ast_reassociate = _make_op("ast_reassociate", _m_assoc, _r_assoc)
mutate_ast_demorgan = _make_op("ast_demorgan", _m_demorgan, _r_demorgan, mutate_demorgan)
mutate_ast_distribute = _make_op("ast_distribute", _m_dist, _r_dist)
mutate_ast_sub_as_add = _make_op("ast_sub_as_add", _m_sub, _r_sub, _regex_sub_as_add)
mutate_ast_ternary_invert = _make_op("ast_ternary_invert", _m_tern, _r_tern, _regex_ternary_invert)
mutate_ast_simplify = _make_op("ast_simplify", _m_simplify, _r_simplify)
mutate_ast_if_ternary = _make_op("ast_if_ternary", _m_ifter, _r_ifter)


# --------------------------------------------------------------------------- module-level operators
def _label_values(case: Case, params: dict):
    vals = []
    for it in case.items:
        if it.labels is None:
            continue
        for l in it.labels:
            if isinstance(l, Num) and l.value is not None:
                vals.append(l.value)
            elif isinstance(l, Ident) and l.name in params:
                vals.append(params[l.name])
            else:
                return None
    return vals


def mutate_ast_case_reorder(source: str, rng: random.Random) -> Tuple[str, Mutation]:
    """Permute the branches of a plain `case` whose labels are distinct constants (order-independent)."""
    kind = "ast_case_reorder"
    sf = _parse(source)
    if sf is None:
        return _noop(kind, "source outside the supported Verilog subset", source)
    cands: List[Tuple[int, int]] = []
    for mi, mod in enumerate(sf.modules):
        try:
            params = Widths(mod).params
        except UnsupportedSyntax:
            continue

        def m(n, params=params):
            if isinstance(n, Case) and n.kind == "case" and len(n.items) >= 3:
                v = _label_values(n, params)
                return v is not None and len(set(v)) == len(v)
            return False
        for j in range(_count(mod, m)):
            cands.append((mi, j))
    if not cands:
        return _noop(kind, "no plain case with distinct constant labels", source)
    mi, j = rng.choice(cands)
    mod = sf.modules[mi]
    params = Widths(mod).params

    def m2(n):
        if isinstance(n, Case) and n.kind == "case" and len(n.items) >= 3:
            v = _label_values(n, params)
            return v is not None and len(set(v)) == len(v)
        return False

    def r2(n):
        items = list(n.items)
        for _ in range(8):
            rng.shuffle(items)
            if items != n.items:
                break
        return Case(n.kind, n.expr, items)
    sf.modules[mi] = _replace_nth(mod, m2, r2, j)
    return print_source(sf), Mutation(kind, f"reordered case branches (module {mod.name})")


def _blocking_or_comb_assigned(mod: Module) -> set:
    names = set()

    def grab(lhs):
        if isinstance(lhs, Ident):
            names.add(lhs.name)
        elif isinstance(lhs, Select):
            grab(lhs.base)
        elif hasattr(lhs, "parts"):
            for p in lhs.parts:
                grab(p)

    def visit(s, in_comb):
        if isinstance(s, Assign):
            if s.blocking or in_comb:
                grab(s.lhs)
        elif isinstance(s, Block):
            for x in s.stmts:
                visit(x, in_comb)
        elif isinstance(s, If):
            visit(s.then, in_comb)
            if s.other is not None:
                visit(s.other, in_comb)
        elif isinstance(s, Case):
            for it in s.items:
                visit(it.body, in_comb)

    for it in mod.items:
        if isinstance(it, Always):
            edged = it.sens is not None and any(e for e, _ in it.sens)
            visit(it.body, not edged)
    return names


def mutate_ast_cse(source: str, rng: random.Random) -> Tuple[str, Mutation]:
    """Extract a repeated bitwise sub-expression (a&b, a|b, a^b over side-effect-free operands) into a wire."""
    kind = "ast_cse"
    sf = _parse(source)
    if sf is None:
        return _noop(kind, "source outside the supported Verilog subset", source)
    options = []
    for mi, mod in enumerate(sf.modules):
        try:
            W = Widths(mod)
        except UnsupportedSyntax:
            continue
        bad = _blocking_or_comb_assigned(mod)

        def operand_ok(x):
            if isinstance(x, Ident):
                return x.name in W.sig and x.name not in bad
            if isinstance(x, Select) and x.mode in ("bit", "part") and isinstance(x.base, Ident):
                try:
                    if x.mode == "part":
                        W.const(x.hi), W.const(x.lo)
                    else:
                        W.const(x.hi)
                except UnsupportedSyntax:
                    return False
                return x.base.name in W.sig and x.base.name not in bad
            return False

        def m(e):
            return isinstance(e, Binary) and e.op in ("&", "|", "^") and operand_ok(e.left) and operand_ok(e.right)

        tally: dict = {}
        exemplar: dict = {}

        def collect(e):
            if m(e):
                key = pe(e)
                tally[key] = tally.get(key, 0) + 1
                exemplar.setdefault(key, copy.deepcopy(e))
            return False
        _walk(copy.deepcopy(mod), {"n": 0, "target": -1}, collect, lambda x: x)
        for key, cnt in tally.items():
            if cnt >= 2:
                options.append((mi, key, exemplar[key], W))
    if not options:
        return _noop(kind, "no repeated bitwise sub-expression over safe operands", source)
    mi, key, ex, W = rng.choice(options)
    mod = sf.modules[mi]
    width = max(self_width(ex.left, W), self_width(ex.right, W))
    n = 0
    while f"_cse{n}" in W.sig:
        n += 1
    name = f"_cse{n}"

    def mm(e):
        return isinstance(e, Binary) and pe(e) == key

    # replace every occurrence (rewrite at each match; loop until none remain outside the new decl)
    while _count(mod, mm) > 0:
        mod = _replace_nth(mod, mm, lambda e: Ident(name), 0)
    last_decl = max((i for i, it in enumerate(mod.items) if isinstance(it, (PortDecl, NetDecl, ParamDecl))), default=-1)
    decl = NetDecl("wire", False, (Num(str(width - 1), None, width - 1), Num("0", None, 0)), [(name, ex)])
    mod.items.insert(last_decl + 1, decl)
    sf.modules[mi] = mod
    return print_source(sf), Mutation(kind, f"extracted '{key}' into wire {name}[{width - 1}:0]")


AST_OPERATORS = [
    mutate_ast_commutative, mutate_ast_reassociate, mutate_ast_demorgan, mutate_ast_distribute,
    mutate_ast_sub_as_add, mutate_ast_ternary_invert, mutate_ast_simplify, mutate_ast_if_ternary,
    mutate_ast_case_reorder, mutate_ast_cse,
]
AST_KIND_NAMES = [
    "ast_commutative", "ast_reassociate", "ast_demorgan", "ast_distribute", "ast_sub_as_add",
    "ast_ternary_invert", "ast_simplify", "ast_if_ternary", "ast_case_reorder", "ast_cse",
]
