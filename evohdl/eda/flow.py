"""flow.py -- the end-to-end native flow on one AIG: optimize -> verify -> map -> verify -> STA -> power."""
from __future__ import annotations

import time
from typing import Optional

from evohdl.eda.aig import Aig
from evohdl.eda.cec import CecResult, bmc_equiv, combinational_equiv, sequential_equiv_matched
from evohdl.eda.liberty import Library
from evohdl.eda.netlist import Netlist
from evohdl.eda.opt import optimize
from evohdl.eda.sta import Constraints, analyze, estimate_power, parse_sdc
from evohdl.eda.techmap import techmap

FLOW_VERSION = "eda-flow-1"


def sim_check(a: Aig, b: Aig, nbits: int = 4096, seed: int = 11) -> CecResult:
    """Random-simulation comparison (outputs and next-state functions). NEVER a proof: a pass is reported as
    status SIM_ONLY, a mismatch is a real NOT_EQUIVALENT with the failing pattern as counterexample."""
    ins = a.random_patterns(nbits, seed)
    st = {l["name"]: v for l, v in zip(a.latches, [__import__("random").Random(seed + i).getrandbits(nbits)
                                                    for i in range(len(a.latches))])}
    oa, na, _ = a.simulate(ins, st, nbits)
    ob, nb, _ = b.simulate(ins, st, nbits)
    for k in oa:
        if oa[k] != ob.get(k):
            bit = ((oa[k] ^ ob[k]) & -(oa[k] ^ ob[k])).bit_length() - 1
            return CecResult("NOT_EQUIVALENT", "random-sim", f"output {k} differs", {n: (v >> bit) & 1 for n, v in ins.items()})
    for k in na:
        if na[k] != nb.get(k):
            return CecResult("NOT_EQUIVALENT", "random-sim", f"next-state of {k} differs")
    return CecResult("SIM_ONLY", f"random-sim-{nbits}", "no difference found in random simulation (NOT a proof)")


def verify(a: Aig, b: Aig, conflict_limit: int = 8000, bmc_k: int = 8) -> CecResult:
    """Strongest check available within the conflict budget: combinational SAT miter; sequential latch-matched proof,
    else bounded BMC; if the solver gives up (UNKNOWN) fall back to random simulation and say so (SIM_ONLY)."""
    if not a.latches and not b.latches:
        r = combinational_equiv(a, b, conflict_limit)
    else:
        r = sequential_equiv_matched(a, b, conflict_limit)
        if r.status != "EQUIVALENT":
            bm = bmc_equiv(a, b, bmc_k, conflict_limit)
            if bm.status == "EQUIVALENT":
                bm.reason = f"latch-matched proof failed ({r.reason or r.status}); {bm.reason}"
            r = bm
    if r.status == "UNKNOWN":
        s = sim_check(a, b)
        s.reason = f"SAT gave up ({r.reason}); {s.reason}"
        return s
    return r


def run_flow(aig: Aig, lib: Library, name: str = "top", effort: int = 2, objective: str = "area",
             period: float = 2.0, sdc_text: Optional[str] = None, conflict_limit: int = 8000) -> dict:
    t0 = time.time()
    before = aig.cleanup()
    opt = optimize(before, effort=effort)
    v_opt = verify(before, opt, conflict_limit)
    nl = techmap(opt, lib, objective, name)
    v_map = verify(opt, nl.to_aig(lib), conflict_limit)
    cons = parse_sdc(sdc_text, nl) if sdc_text else Constraints(period=period, clock_port=nl.clock)
    sta = analyze(nl, lib, cons)
    pw = estimate_power(nl, lib, cons)
    return {
        "name": name, "ands_before": before.num_ands(), "ands_after": opt.num_ands(),
        "depth_before": before.depth(), "depth_after": opt.depth(),
        "cells": len(nl.cells), "area": round(nl.area(lib), 3), "flops": nl.stats(lib)["flops"],
        "wns": round(sta.wns, 5), "min_period": round(sta.min_period, 5), "power_uW": round(pw["total_uW"], 4),
        "verify_opt": v_opt.status, "verify_opt_method": v_opt.method,
        "verify_map": v_map.status, "verify_map_method": v_map.method,
        "verified": "NOT_EQUIVALENT" if "NOT_EQUIVALENT" in (v_opt.status, v_map.status) else
                    "EQUIVALENT" if v_opt.status == v_map.status == "EQUIVALENT" else "SIM_ONLY",
        "seconds": round(time.time() - t0, 3), "netlist": nl, "sta": sta, "opt_aig": opt,
    }
