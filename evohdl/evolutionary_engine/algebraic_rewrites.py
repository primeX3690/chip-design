"""
algebraic_rewrites.py
----------------------
Structure-aware, *semantics-preserving* Verilog rewrites (gap F). Unlike operator_swap /
constant_tweak (which change what the circuit computes and are almost always rejected), these
are identities: commutativity, De Morgan, subtract-as-add, ternary inversion. They keep the
genome syntactically valid and move it to a different-but-equivalent text, which changes how
later Yosys/ABC passes see the logic (neutral drift between optimization basins).

Honest expectation: Yosys canonicalizes many of these, so on their own they rarely change the
cell count. Their value is diversity for the pass-pipeline operator and crossover. They are
"intended" identities and are never trusted blindly: the fitness gate (formal equivalence or
simulation) still decides whether a mutant is accepted.

Scope: matches simple operands (identifier, optionally one bit/part select) on single lines. It is
regex-based, not an AST (see README "Current limitations").
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import List, Tuple

ATOM = r"[A-Za-z_]\w*(?:\[\d+(?::\d+)?\])?"


@dataclass
class Mutation:
    kind: str
    description: str


def _noop(kind: str, why: str, source: str) -> Tuple[str, Mutation]:
    return source, Mutation(kind, f"no-op: {why}")


def _pick_span(source: str, pattern: re.Pattern, rng: random.Random):
    matches = list(pattern.finditer(source))
    return rng.choice(matches) if matches else None


# a = b OP c  /  assign x = b OP c  (lhs may be a concatenation; excludes `<=` and `==`)
_COMM_RE = re.compile(
    rf"^(?P<pre>[ \t]*(?:assign\s+)?[^=;<>!\n]+?=\s*)(?P<a>{ATOM})\s*(?P<op>[&|^+])\s*(?P<b>{ATOM})(?P<post>\s*;)",
    re.MULTILINE,
)


def mutate_commutative_swap(source: str, rng: random.Random) -> Tuple[str, Mutation]:
    cands = [m for m in _COMM_RE.finditer(source) if m.group("a") != m.group("b")]
    if not cands:
        return _noop("commutative_swap", "no `x = a OP b` with OP in & | ^ + found", source)
    m = rng.choice(cands)
    new = f'{m.group("pre")}{m.group("b")} {m.group("op")} {m.group("a")}{m.group("post")}'
    return source[:m.start()] + new + source[m.end():], Mutation(
        "commutative_swap", f"swapped operands of '{m.group('op')}': {m.group('a')} <-> {m.group('b')}")


_DM_NOT_OUTER = re.compile(rf"~\(\s*(?P<a>{ATOM})\s*(?P<op>[&|])\s*(?P<b>{ATOM})\s*\)")
_DM_NOT_INNER = re.compile(rf"\(\s*~(?P<a>{ATOM})\s*(?P<op>[&|])\s*~(?P<b>{ATOM})\s*\)")


def mutate_demorgan(source: str, rng: random.Random) -> Tuple[str, Mutation]:
    """~(a & b) <-> (~a | ~b),  ~(a | b) <-> (~a & ~b)  (either direction)."""
    cands: List[Tuple[re.Match, str]] = []
    for m in _DM_NOT_OUTER.finditer(source):
        flip = "|" if m.group("op") == "&" else "&"
        cands.append((m, f"(~{m.group('a')} {flip} ~{m.group('b')})"))
    for m in _DM_NOT_INNER.finditer(source):
        flip = "|" if m.group("op") == "&" else "&"
        # (~a OP ~b) == ~(a OPposite b)
        cands.append((m, f"~({m.group('a')} {flip} {m.group('b')})"))
    if not cands:
        return _noop("demorgan", "no ~(a&b) / (~a|~b) pattern found", source)
    m, repl = rng.choice(cands)
    return source[:m.start()] + repl + source[m.end():], Mutation(
        "demorgan", f"De Morgan: '{m.group(0)}' -> '{repl}'")


_SUB_RE = re.compile(rf"(?P<a>{ATOM})\s+-\s+(?P<b>{ATOM})(?=\s*[;)])")


def mutate_sub_as_add(source: str, rng: random.Random) -> Tuple[str, Mutation]:
    """a - b  ->  a + ~b + 1'b1  (two's complement identity at any common context width)."""
    m = _pick_span(source, _SUB_RE, rng)
    if not m:
        return _noop("sub_as_add", "no `a - b` of simple operands found", source)
    repl = f"{m.group('a')} + ~{m.group('b')} + 1'b1"
    return source[:m.start()] + repl + source[m.end():], Mutation(
        "sub_as_add", f"'{m.group(0)}' -> '{repl}'")


_TERN_RE = re.compile(
    rf"(?P<pre>=\s*)(?P<c>{ATOM})\s*\?\s*(?P<x>{ATOM})\s*:\s*(?P<y>{ATOM})(?P<post>\s*;)"
)


def mutate_ternary_invert(source: str, rng: random.Random) -> Tuple[str, Mutation]:
    """c ? x : y  ->  (!c) ? y : x   (logical-not of the select, branches swapped)."""
    m = _pick_span(source, _TERN_RE, rng)
    if not m:
        return _noop("ternary_invert", "no simple `c ? x : y` found", source)
    repl = f"{m.group('pre')}(!{m.group('c')}) ? {m.group('y')} : {m.group('x')}{m.group('post')}"
    return source[:m.start()] + repl + source[m.end():], Mutation(
        "ternary_invert", f"inverted select of ternary on '{m.group('c')}'")


ALGEBRAIC_OPERATORS = [
    mutate_commutative_swap, mutate_demorgan, mutate_sub_as_add, mutate_ternary_invert,
]
ALGEBRAIC_KIND_NAMES = ["commutative_swap", "demorgan", "sub_as_add", "ternary_invert"]
