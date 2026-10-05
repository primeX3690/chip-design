"""
benchmarks.py -- benchmark circuits for the EDA kernel.

IMPORTANT (honest scope): the original ISCAS-85 / EPFL / OpenCores suites could not be downloaded in the environment
this was written in (no network). What IS here: ISCAS-85 `c17` (6 NAND gates, reproduced exactly), a set of parametric
generators for the circuit FAMILIES those suites are built from (adders, multipliers, comparators, parity, mux trees,
priority encoders, barrel shifters, popcount), deliberately-redundant variants that exercise the optimizer, and the
project's own RTL seeds. To use the real suites: put `.bench` / `.aag` files in `benchmarks/external/` and run
`python -m evohdl.eda bench run-dir benchmarks/external` (see docs/EDA_KERNEL.md).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List

from evohdl.eda.aig import Aig, FALSE, TRUE
from evohdl.eda.bench_io import read_bench
from evohdl.eda.elaborate import add_bits, mul_bits, shift_var, eq_bits, lt_bits, mux_bits

C17 = """# ISCAS-85 c17
INPUT(1)
INPUT(2)
INPUT(3)
INPUT(6)
INPUT(7)
OUTPUT(22)
OUTPUT(23)
10 = NAND(1, 3)
11 = NAND(3, 6)
16 = NAND(2, 11)
19 = NAND(11, 7)
22 = NAND(10, 16)
23 = NAND(16, 19)
"""


def _vec(g: Aig, name: str, n: int) -> List[int]:
    return [g.new_input(f"{name}{i}") for i in range(n)]


def ripple_adder(n: int) -> Aig:
    g = Aig()
    a, b = _vec(g, "a", n), _vec(g, "b", n)
    s, c = add_bits(g, a, b)
    for i, l in enumerate(s):
        g.add_output(f"s{i}", l)
    g.add_output("cout", c)
    return g


def array_multiplier(n: int) -> Aig:
    g = Aig()
    a, b = _vec(g, "a", n), _vec(g, "b", n)
    for i, l in enumerate(mul_bits(g, a, b, 2 * n)):
        g.add_output(f"p{i}", l)
    return g


def comparator(n: int) -> Aig:
    g = Aig()
    a, b = _vec(g, "a", n), _vec(g, "b", n)
    g.add_output("eq", eq_bits(g, a, b))
    g.add_output("lt", lt_bits(g, a, b))
    g.add_output("gt", lt_bits(g, b, a))
    return g


def parity_tree(n: int) -> Aig:
    g = Aig()
    xs = _vec(g, "x", n)
    r = FALSE
    for x in xs:                       # deliberately a linear chain (deep); balance should fix the depth
        r = g.XOR(r, x)
    g.add_output("parity", r)
    return g


def mux_tree(sel_bits: int) -> Aig:
    g = Aig()
    data = _vec(g, "d", 1 << sel_bits)
    sel = _vec(g, "s", sel_bits)
    cur = data
    for s in sel:
        cur = [g.MUX(s, cur[2 * i + 1], cur[2 * i]) for i in range(len(cur) // 2)]
    g.add_output("y", cur[0])
    return g


def priority_encoder(n: int) -> Aig:
    """Index of the highest set request bit; `valid` = any request."""
    g = Aig()
    r = _vec(g, "r", n)
    k = max(1, (n - 1).bit_length())
    code = [FALSE] * k
    for i in range(n):
        higher_none = g.AND_many([r[m] ^ 1 for m in range(i + 1, n)])
        hit = g.AND(r[i], higher_none)
        for j in range(k):
            if (i >> j) & 1:
                code[j] = g.OR(code[j], hit)
    g.add_output("valid", g.OR_many(r))
    for j, c in enumerate(code):
        g.add_output(f"idx{j}", c)
    return g


def barrel_shifter(n: int) -> Aig:
    g = Aig()
    x = _vec(g, "x", n)
    amt = _vec(g, "k", max(1, (n - 1).bit_length()))
    for i, l in enumerate(shift_var(g, x, amt, True)):
        g.add_output(f"y{i}", l)
    return g


def popcount(n: int) -> Aig:
    g = Aig()
    xs = _vec(g, "x", n)
    w = n.bit_length()
    acc = [FALSE] * w
    for x in xs:
        acc, _ = add_bits(g, acc, [x] + [FALSE] * (w - 1))
    for i, l in enumerate(acc):
        g.add_output(f"c{i}", l)
    return g


def redundant_logic(n: int = 10, seed: int = 3) -> Aig:
    """Random logic whose cones are each computed twice in different (but equivalent) forms. A good optimizer should
    merge the copies; the exact saving is whatever the optimizer finds, not a promised number."""
    rng = random.Random(seed)
    g = Aig()
    xs = _vec(g, "x", n)
    for k in range(6):
        a, b, c, d = (xs[rng.randrange(n)] for _ in range(4))
        f1 = g.OR(g.AND(a, b), g.AND(a, c))                 # a&b | a&c
        f2 = g.AND(a, g.OR(b, c))                           # a&(b|c)
        h1 = g.XOR(f1, g.AND(c, d))
        h2 = g.OR(g.AND(f2, g.AND(c, d) ^ 1), g.AND(f2 ^ 1, g.AND(c, d)))
        g.add_output(f"o{k}", g.XOR(h1, h2) ^ 1 if k % 2 else g.AND(h1, h2))
    return g


@dataclass
class Benchmark:
    name: str
    build: Callable[[], Aig]
    family: str
    note: str = ""


def _rtl(name: str) -> Callable[[], Aig]:
    def build() -> Aig:
        from evohdl.eda.elaborate import elaborate
        from evohdl.paths import SEED_DIR
        return elaborate((SEED_DIR / f"{name}.v").read_text(), name)
    return build


BENCHMARKS: Dict[str, Benchmark] = {b.name: b for b in [
    Benchmark("c17", lambda: read_bench(C17, "c17"), "iscas85", "exact ISCAS-85 c17"),
    Benchmark("adder8", lambda: ripple_adder(8), "arith"), Benchmark("adder16", lambda: ripple_adder(16), "arith"),
    Benchmark("mult4", lambda: array_multiplier(4), "arith"), Benchmark("mult6", lambda: array_multiplier(6), "arith"),
    Benchmark("cmp8", lambda: comparator(8), "arith"), Benchmark("parity16", lambda: parity_tree(16), "random-control"),
    Benchmark("mux16", lambda: mux_tree(4), "control"), Benchmark("prio8", lambda: priority_encoder(8), "control"),
    Benchmark("shift8", lambda: barrel_shifter(8), "arith"), Benchmark("popcount8", lambda: popcount(8), "arith"),
    Benchmark("redundant10", lambda: redundant_logic(10), "redundant", "optimizer stress"),
    Benchmark("alu_basic", _rtl("alu_basic"), "rtl-seed"), Benchmark("comparator_4bit", _rtl("comparator_4bit"), "rtl-seed"),
    Benchmark("counter_4bit", _rtl("counter_4bit"), "rtl-seed-seq"), Benchmark("fsm_seqdet", _rtl("fsm_seqdet"), "rtl-seed-seq"),
    Benchmark("mult_seq8", _rtl("mult_seq8"), "rtl-seed-seq"),
]}
