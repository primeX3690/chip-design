"""bench_io.py -- readers/writers for ISCAS `.bench` and ASCII AIGER (`.aag`), the formats ISCAS/EPFL-style benchmark
suites are distributed in. (Binary `.aig`: convert with `aigtoaig`; EPFL also ships Verilog/BLIF -> use `elab`/yosys.)"""
from __future__ import annotations

import re
from typing import Dict, List

from evohdl.eda.aig import Aig, FALSE, TRUE


def read_bench(text: str, name: str = "bench") -> Aig:
    g = Aig()
    sig: Dict[str, int] = {}
    defs: Dict[str, tuple] = {}
    outs: List[str] = []
    inputs: List[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"(?i)INPUT\s*\(\s*([^)\s]+)\s*\)", line)
        if m:
            inputs.append(m.group(1))
            continue
        m = re.match(r"(?i)OUTPUT\s*\(\s*([^)\s]+)\s*\)", line)
        if m:
            outs.append(m.group(1))
            continue
        m = re.match(r"([^\s=]+)\s*=\s*(\w+)\s*\(([^)]*)\)", line)
        if not m:
            raise ValueError(f"cannot parse .bench line: {line!r}")
        defs[m.group(1)] = (m.group(2).upper(), [a.strip() for a in m.group(3).split(",") if a.strip()])
    for n in inputs:
        sig[n] = g.new_input(n)
    latches = {}
    for n, (op, args) in defs.items():
        if op == "DFF":
            sig[n] = g.new_latch(n, 0)
            latches[n] = args[0]

    def build(n: str, stack=()) -> int:
        if n in sig:
            return sig[n]
        if n in stack:
            raise ValueError(f"combinational loop at {n}")
        if n not in defs:
            raise ValueError(f"undefined signal {n}")
        op, args = defs[n]
        vals = [build(a, stack + (n,)) for a in args]
        if op in ("AND", "NAND"):
            r = g.AND_many(vals)
        elif op in ("OR", "NOR"):
            r = g.OR_many(vals)
        elif op in ("XOR", "XNOR"):
            r = FALSE
            for v in vals:
                r = g.XOR(r, v)
        elif op in ("NOT", "INV"):
            r = vals[0] ^ 1
        elif op in ("BUF", "BUFF"):
            r = vals[0]
        else:
            raise ValueError(f"unsupported gate type {op}")
        if op in ("NAND", "NOR", "XNOR"):
            r ^= 1
        sig[n] = r
        return r

    for n in outs:
        g.add_output(n, build(n))
    for n, d in latches.items():
        g.set_latch_next(sig[n], build(d))
    return g


def write_bench(g: Aig) -> str:
    lines = [f"INPUT({n})" for n, _ in g.inputs] + [f"OUTPUT({n})" for n, _ in g.outputs]
    name = {0: "const0"}
    for n, l in g.inputs:
        name[l >> 1] = n
    for l in g.latches:
        name[l["q"] >> 1] = l["name"]
    body: List[str] = ["const0 = AND(%s, NOT_%s)" % (g.inputs[0][0], g.inputs[0][0])] if g.inputs else []
    if g.inputs:
        body.insert(0, f"NOT_{g.inputs[0][0]} = NOT({g.inputs[0][0]})")

    def ref(l: int) -> str:
        v = l >> 1
        base = name[v]
        if not (l & 1):
            return base
        inv = f"{base}_n"
        if inv not in emitted:
            emitted.add(inv)
            body.append(f"{inv} = NOT({base})")
        return inv

    emitted: set = set()
    for v in g._reachable():
        if g.kind[v] == "a":
            name[v] = f"n{v}"
            a, b = ref(g.f0[v]), ref(g.f1[v])
            body.append(f"n{v} = AND({a}, {b})")
    for l in g.latches:
        body.append(f"{l['name']} = DFF({ref(l['next'])})")
    taken = {n for n, _ in g.inputs} | {l["name"] for l in g.latches}
    for n, l in g.outputs:
        r = ref(l)
        if r == n:
            continue                      # output is directly an input / register of the same name
        if n in taken:
            raise ValueError(f"output '{n}' collides with an input/register name; .bench cannot express that")
        body.append(f"{n} = BUFF({r})")
    return "\n".join(lines + body) + "\n"


def write_aag(g: Aig) -> str:
    g = g.cleanup()
    var = {0: 0}
    k = 0
    for _, lit in g.inputs:
        k += 1
        var[lit >> 1] = k
    for l in g.latches:
        k += 1
        var[l["q"] >> 1] = k
    ands = [v for v in range(1, g.size) if g.kind[v] == "a"]
    for v in ands:
        k += 1
        var[v] = k
    L = lambda lit: 2 * var[lit >> 1] + (lit & 1)
    out = [f"aag {k} {len(g.inputs)} {len(g.latches)} {len(g.outputs)} {len(ands)}"]
    out += [str(2 * var[l >> 1]) for _, l in g.inputs]
    for l in g.latches:
        out.append(f"{2 * var[l['q'] >> 1]} {L(l['next'])}" + (" 1" if l["init"] else ""))
    out += [str(L(l)) for _, l in g.outputs]
    out += [f"{2 * var[v]} {L(g.f0[v])} {L(g.f1[v])}" for v in ands]
    out += [f"i{i} {n}" for i, (n, _) in enumerate(g.inputs)]
    out += [f"l{i} {l['name']}" for i, l in enumerate(g.latches)]
    out += [f"o{i} {n}" for i, (n, _) in enumerate(g.outputs)]
    return "\n".join(out) + "\n"


def read_aag(text: str) -> Aig:
    lines = [l for l in text.splitlines() if l.strip()]
    hdr = lines[0].split()
    if hdr[0] != "aag":
        raise ValueError("not an ASCII AIGER file (binary .aig needs conversion with `aigtoaig`)")
    M, I, Lc, O, A = map(int, hdr[1:6])
    pos = 1
    in_lits = [int(lines[pos + i]) for i in range(I)]
    pos += I
    lat = [lines[pos + i].split() for i in range(Lc)]
    pos += Lc
    out_lits = [int(lines[pos + i].split()[0]) for i in range(O)]
    pos += O
    gates = {int(p[0]): (int(p[1]), int(p[2])) for p in (lines[pos + i].split() for i in range(A))}
    pos += A
    names = {"i": {}, "l": {}, "o": {}}
    for ln in lines[pos:]:
        if ln.startswith("c"):
            break
        m = re.match(r"([ilo])(\d+)\s+(.+)", ln)
        if m:
            names[m.group(1)][int(m.group(2))] = m.group(3).strip()
    g = Aig()
    lit: Dict[int, int] = {0: FALSE, 1: TRUE}
    for i, l in enumerate(in_lits):
        lit[l] = g.new_input(names["i"].get(i, f"i{i}"))
        lit[l ^ 1] = lit[l] ^ 1
    for i, p in enumerate(lat):
        q = g.new_latch(names["l"].get(i, f"l{i}"), int(p[2]) if len(p) > 2 else 0)
        lit[int(p[0])] = q
        lit[int(p[0]) ^ 1] = q ^ 1

    def get(l: int) -> int:
        if l in lit:
            return lit[l]
        base = l & ~1
        a, b = gates[base]
        r = g.AND(get(a), get(b))
        lit[base], lit[base ^ 1] = r, r ^ 1
        return lit[l]

    for i, l in enumerate(out_lits):
        g.add_output(names["o"].get(i, f"o{i}"), get(l))
    for p, ln in zip(lat, g.latches):
        ln["next"] = get(int(p[1]))
    return g
