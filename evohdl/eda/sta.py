"""
sta.py -- static timing analysis (setup, single clock, ideal clock network) + SDC subset + switching-activity power.

Model: NLDM table lookup per arc (input slew x output load) with separate rise/fall arrival and slew per net,
unateness-aware propagation (positive / negative / non-unate), launch at input ports (set_input_delay) and DFF
clk->Q, capture at output ports (set_output_delay) and DFF D (setup constraint tables). Net load = sum of sink pin
capacitances + a per-fanout wire estimate + set_load on output ports.

NOT modelled (stated plainly): hold analysis, clock tree / skew / uncertainty beyond a flat number, multiple clocks
or clock domain crossings, false/multicycle paths, OCV/derating, wire RC / parasitics, crosstalk, MMMC corners.
SDC commands understood: create_clock, set_input_delay, set_output_delay, set_load, set_input_transition,
set_clock_uncertainty (with get_ports / all_inputs / all_outputs and * ? wildcards).
"""
from __future__ import annotations

import re
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from evohdl.eda.liberty import LibCell, Library, Table, TimingArc
from evohdl.eda.netlist import CONST0, CONST1, NCell, Netlist

WIRE_CAP_PER_FANOUT = 0.0015     # pF, flat wire estimate


# ---------------------------------------------------------------------------- SDC
@dataclass
class Constraints:
    period: float = 10.0
    clock_port: Optional[str] = None
    clock_name: str = "clk"
    uncertainty: float = 0.0
    input_delay: Dict[str, float] = field(default_factory=dict)
    output_delay: Dict[str, float] = field(default_factory=dict)
    load: Dict[str, float] = field(default_factory=dict)
    default_input_delay: float = 0.0
    default_output_delay: float = 0.0
    default_load: float = 0.005
    input_transition: float = 0.05


def _glob(pattern: str, names: List[str]) -> List[str]:
    rx = re.compile("^" + "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern) + "$")
    return [n for n in names if rx.match(n)]


def parse_sdc(text: str, nl: Netlist) -> Constraints:
    c = Constraints()
    in_ports = [n for n in nl.inputs if n != nl.clock]
    all_ports = list(nl.inputs) + list(nl.outputs)

    def ports_of(arg: str) -> List[str]:
        arg = arg.strip()
        if "all_inputs" in arg:
            return in_ports
        if "all_outputs" in arg:
            return list(nl.outputs)
        m = re.search(r"get_ports\s+(\{[^}]*\}|\S+)", arg)
        if not m:
            return []
        out: List[str] = []
        for pat in m.group(1).strip("{}").split():
            out += _glob(pat, all_ports)
        return out

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        cmd = line.split()[0]
        br = re.findall(r"\[[^\]]*\]", line)
        rest = re.sub(r"\[[^\]]*\]", " ", line)
        nums = re.findall(r"(?<![\w.])[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(?![\w])", rest)
        if cmd == "create_clock":
            m = re.search(r"-period\s+([-\d.eE+]+)", line)
            if not m:
                raise ValueError(f"create_clock without -period: {line}")
            c.period = float(m.group(1))
            n = re.search(r"-name\s+(\S+)", line)
            if n:
                c.clock_name = n.group(1)
            tgt = ports_of(br[0]) if br else []
            c.clock_port = tgt[0] if tgt else nl.clock
        elif cmd in ("set_input_delay", "set_output_delay"):
            d = float(nums[0]) if nums else 0.0
            tgt = ports_of(br[-1]) if br else []
            store = c.input_delay if cmd == "set_input_delay" else c.output_delay
            for p in tgt:
                store[p] = d
        elif cmd == "set_load":
            val = float(nums[0]) if nums else 0.0
            for p in (ports_of(br[-1]) if br else list(nl.outputs)):
                c.load[p] = val
        elif cmd == "set_input_transition":
            c.input_transition = float(nums[0]) if nums else c.input_transition
        elif cmd == "set_clock_uncertainty":
            c.uncertainty = float(nums[0]) if nums else 0.0
    if c.clock_port is None:
        c.clock_port = nl.clock
    return c


# ---------------------------------------------------------------------------- analysis
@dataclass
class PathStep:
    net: str
    cell: str
    pin: str
    edge: str
    arrival: float


@dataclass
class StaReport:
    period: float
    wns: float
    tns: float
    endpoints: List[dict]
    critical_path: List[PathStep]
    startpoints: int
    min_period: float
    notes: List[str] = field(default_factory=list)

    @property
    def met(self) -> bool:
        return self.wns >= 0

    def summary(self) -> str:
        worst = self.endpoints[0] if self.endpoints else {}
        return (f"period {self.period:.3f} ns | WNS {self.wns:+.4f} ns | TNS {self.tns:+.4f} ns | "
                f"{'MET' if self.met else 'VIOLATED'} | endpoints {len(self.endpoints)} | worst endpoint {worst.get('endpoint', '-')}"
                f" | min period ~{self.min_period:.3f} ns (~{1000.0 / self.min_period:.1f} MHz)" if self.min_period > 0 else "no timing paths")


def _arcs_for(cell: LibCell, out_pin: str, in_pin: str) -> Optional[TimingArc]:
    for a in cell.pins[out_pin].arcs:
        if a.related_pin == in_pin and a.timing_type in ("combinational", "rising_edge", "falling_edge"):
            return a
    return None


EDGES = ("r", "f")


def net_loads(nl: Netlist, lib: Library, cons: Constraints) -> Dict[str, float]:
    load: Dict[str, float] = {}
    for c in nl.cells:
        lc = lib.cells[c.type]
        for p in lc.input_pins:
            net = nl.resolve(c.pins[p])
            load[net] = load.get(net, 0.0) + lc.pins[p].capacitance + WIRE_CAP_PER_FANOUT
    for o in nl.outputs:
        net = nl.resolve(nl.aliases.get(o, o))
        load[net] = load.get(net, 0.0) + cons.load.get(o, cons.default_load)
    return load


def analyze(nl: Netlist, lib: Library, cons: Optional[Constraints] = None) -> StaReport:
    cons = cons or Constraints()
    load = net_loads(nl, lib, cons)
    arr: Dict[Tuple[str, str], float] = {}
    slew: Dict[Tuple[str, str], float] = {}
    pred: Dict[Tuple[str, str], Optional[tuple]] = {}
    notes: List[str] = []

    def setnet(net: str, a: float, s: float, edge_set=EDGES, p=None):
        for e in edge_set:
            arr[(net, e)], slew[(net, e)], pred[(net, e)] = a, s, p

    starts = 0
    for n in nl.inputs:
        if n == nl.clock or n == cons.clock_port:
            continue
        setnet(n, cons.input_delay.get(n, cons.default_input_delay), cons.input_transition)
        starts += 1
    setnet(CONST0, 0.0, 0.0)
    setnet(CONST1, 0.0, 0.0)

    for c in nl.cells:
        lc = lib.cells[c.type]
        if not lc.is_ff:
            continue
        q = c.pins["Q"]
        arc = _arcs_for(lc, "Q", "CLK")
        L = load.get(q, WIRE_CAP_PER_FANOUT)
        for e in EDGES:
            if arc and ("cell_rise" if e == "r" else "cell_fall") in arc.tables:
                d = arc.tables["cell_rise" if e == "r" else "cell_fall"].lookup(cons.input_transition, L)
                s = arc.tables["rise_transition" if e == "r" else "fall_transition"].lookup(cons.input_transition, L)
            else:
                d, s = 0.1, cons.input_transition
            arr[(q, e)], slew[(q, e)], pred[(q, e)] = d, s, ("launch", c, "CLK", None, None, d)
        starts += 1

    for c in nl.topo_cells(lib):
        lc = lib.cells[c.type]
        if lc.is_ff:
            continue
        out_pin = lc.output_pins[0]
        out_net = c.pins[out_pin]
        L = load.get(out_net, WIRE_CAP_PER_FANOUT)
        best: Dict[str, Tuple[float, float, tuple]] = {}
        for ip in lc.input_pins:
            arc = _arcs_for(lc, out_pin, ip)
            if arc is None:
                continue
            in_net = nl.resolve(c.pins[ip])
            if (in_net, "r") not in arr:
                arr[(in_net, "r")] = arr[(in_net, "f")] = 0.0
                slew[(in_net, "r")] = slew[(in_net, "f")] = cons.input_transition
                pred[(in_net, "r")] = pred[(in_net, "f")] = None
                notes.append(f"net {in_net} has no driver/startpoint; assumed arrival 0")
            pairs = {"positive_unate": [("r", "r"), ("f", "f")], "negative_unate": [("r", "f"), ("f", "r")]}.get(
                arc.sense, [("r", "r"), ("r", "f"), ("f", "r"), ("f", "f")])
            for oe, ie in pairs:
                dk, sk = ("cell_rise", "rise_transition") if oe == "r" else ("cell_fall", "fall_transition")
                if dk not in arc.tables:
                    continue
                d = arc.tables[dk].lookup(slew[(in_net, ie)], L)
                s = arc.tables[sk].lookup(slew[(in_net, ie)], L) if sk in arc.tables else slew[(in_net, ie)]
                a = arr[(in_net, ie)] + d
                if oe not in best or a > best[oe][0]:
                    best[oe] = (a, s, ("comb", c, ip, in_net, ie, d))
        for oe, (a, s, p) in best.items():
            arr[(out_net, oe)], slew[(out_net, oe)], pred[(out_net, oe)] = a, s, p

    endpoints: List[dict] = []
    for o in nl.outputs:
        net = nl.resolve(nl.aliases.get(o, o))
        for e in EDGES:
            if (net, e) not in arr:
                continue
        a = max(arr.get((net, "r"), 0.0), arr.get((net, "f"), 0.0))
        edge = "r" if arr.get((net, "r"), 0.0) >= arr.get((net, "f"), 0.0) else "f"
        req = cons.period - cons.output_delay.get(o, cons.default_output_delay) - cons.uncertainty
        endpoints.append({"endpoint": o, "kind": "output", "net": net, "edge": edge, "arrival": a, "required": req, "slack": req - a})
    for c in nl.cells:
        lc = lib.cells[c.type]
        if not lc.is_ff:
            continue
        net = nl.resolve(c.pins["D"])
        setup_arc = next((a for a in lc.pins["D"].arcs if a.timing_type.startswith("setup")), None)
        for e in EDGES:
            if (net, e) not in arr:
                continue
            su = 0.0
            if setup_arc:
                t = setup_arc.tables.get("rise_constraint" if e == "r" else "fall_constraint")
                if t:
                    su = t.lookup(slew[(net, e)], cons.input_transition)
            req = cons.period - su - cons.uncertainty
            endpoints.append({"endpoint": f"{c.pins['Q']}/D", "kind": "flop", "net": net, "edge": e, "arrival": arr[(net, e)],
                              "required": req, "slack": req - arr[(net, e)]})
    # keep the worse edge per endpoint
    worst: Dict[str, dict] = {}
    for ep in endpoints:
        if ep["endpoint"] not in worst or ep["slack"] < worst[ep["endpoint"]]["slack"]:
            worst[ep["endpoint"]] = ep
    eps = sorted(worst.values(), key=lambda x: x["slack"])
    wns = min((e["slack"] for e in eps), default=0.0)
    tns = sum(min(0.0, e["slack"]) for e in eps)
    path: List[PathStep] = []
    if eps:
        net, edge = eps[0]["net"], eps[0]["edge"]
        while True:
            p = pred.get((net, edge))
            if p is None:
                path.append(PathStep(net, "port", "-", edge, arr.get((net, edge), 0.0)))
                break
            kind, cell_obj, pin, in_net, ie, _d = p
            path.append(PathStep(net, cell_obj.type, pin, edge, arr[(net, edge)]))
            if kind == "launch":
                break
            net, edge = in_net, ie
        path.reverse()
    min_period = (cons.period - wns) if eps else 0.0
    return StaReport(cons.period, wns, tns, eps, path, starts, min_period, notes[:5])


def format_report(rep: StaReport, top: int = 5) -> str:
    lines = ["STA (setup, ideal clock)", rep.summary(), "", "Critical path:"]
    for s in rep.critical_path:
        lines.append(f"  {s.arrival:8.4f} ns  {s.net:<24} via {s.cell}/{s.pin} ({'rise' if s.edge == 'r' else 'fall'})")
    lines += ["", f"Worst {min(top, len(rep.endpoints))} endpoints:"]
    for e in rep.endpoints[:top]:
        lines.append(f"  {e['endpoint']:<24} slack {e['slack']:+.4f}  arrival {e['arrival']:.4f}  required {e['required']:.4f}")
    if rep.notes:
        lines += ["", "Notes: " + "; ".join(rep.notes)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------- power
def estimate_power(nl: Netlist, lib: Library, cons: Optional[Constraints] = None, cycles: int = 64,
                   nbits: int = 64, seed: int = 1) -> dict:
    """Dynamic (switching-activity x C x V^2 x f / 2) + leakage. Activity from random-input bit-parallel simulation;
    reset-like inputs are held inactive. Statistical estimate, not signoff power."""
    cons = cons or Constraints()
    rng = random.Random(seed)
    mask = (1 << nbits) - 1
    load = net_loads(nl, lib, cons)
    held = {}
    for n in nl.inputs:
        if re.search(r"rst|reset", n, re.IGNORECASE):
            held[n] = mask if re.search(r"(_n|n)(\[|$)", n, re.IGNORECASE) else 0
    state: Dict[str, int] = {}
    prev: Optional[Dict[str, int]] = None
    toggles: Dict[str, int] = {}
    for _ in range(cycles):
        vec = {n: (held[n] if n in held else rng.getrandbits(nbits)) for n in nl.inputs}
        outs, state, vals = nl.simulate(lib, vec, state, nbits)
        if prev is not None:
            for net, v in vals.items():
                if net in (CONST0, CONST1):
                    continue
                toggles[net] = toggles.get(net, 0) + bin((v ^ prev.get(net, v)) & mask).count("1")
        prev = vals
    denom = max(1, (cycles - 1) * nbits)
    f_hz = 1e9 / cons.period
    dyn = 0.0
    for net, t in toggles.items():
        dyn += 0.5 * (t / denom) * load.get(net, 0.0) * 1e-12 * lib.voltage ** 2 * f_hz
    leak = sum(lib.cells[c.type].leakage for c in nl.cells) * 1e-9
    avg_act = (sum(toggles.values()) / (len(toggles) * denom)) if toggles else 0.0
    return {"dynamic_uW": dyn * 1e6, "leakage_uW": leak * 1e6, "total_uW": (dyn + leak) * 1e6,
            "avg_activity": avg_act, "freq_MHz": f_hz / 1e6, "vdd": lib.voltage}
