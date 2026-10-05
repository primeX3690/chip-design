"""regress.py -- benchmark regression database (SQLite) + comparison against the previous run of each benchmark."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from evohdl.eda.flow import FLOW_VERSION

SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, flow TEXT, benchmark TEXT, objective TEXT, effort INTEGER,
  ands_before INTEGER, ands_after INTEGER, depth_before INTEGER, depth_after INTEGER, cells INTEGER, area REAL,
  flops INTEGER, wns REAL, min_period REAL, power_uW REAL, verified TEXT, seconds REAL)"""
COLS = ["benchmark", "objective", "effort", "ands_before", "ands_after", "depth_before", "depth_after", "cells", "area",
        "flops", "wns", "min_period", "power_uW", "verified", "seconds"]


def connect(path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute(SCHEMA)
    return con


def previous(con: sqlite3.Connection, benchmark: str, objective: str, effort: int) -> Optional[dict]:
    row = con.execute("SELECT ands_after, area, depth_after, verified FROM runs WHERE benchmark=? AND objective=? AND effort=? "
                      "ORDER BY id DESC LIMIT 1", (benchmark, objective, effort)).fetchone()
    return dict(zip(["ands_after", "area", "depth_after", "verified"], row)) if row else None


def record(con: sqlite3.Connection, rows: List[dict], objective: str, effort: int):
    for r in rows:
        vals = {**r, "objective": objective, "effort": effort, "benchmark": r["name"]}
        con.execute(f"INSERT INTO runs (ts, flow, {','.join(COLS)}) VALUES (?,?,{','.join('?' * len(COLS))})",
                    (time.time(), FLOW_VERSION, *[vals[c] for c in COLS]))
    con.commit()


def find_regressions(con: sqlite3.Connection, rows: List[dict], objective: str, effort: int, tolerance: float = 0.02) -> List[str]:
    """Compare new rows to the previous stored run. Call BEFORE record(). A regression is: not verified equivalent,
    or AND count / area / depth worse than before by more than `tolerance` (fraction)."""
    bad: List[str] = []
    for r in rows:
        if r["verified"] == "NOT_EQUIVALENT":
            bad.append(f"{r['name']}: NOT EQUIVALENT after optimization/mapping (correctness bug)")
        prev = previous(con, r["name"], objective, effort)
        if not prev:
            continue
        for key, label in (("ands_after", "AND nodes"), ("area", "cell area"), ("depth_after", "depth")):
            if prev[key] and r[key] > prev[key] * (1 + tolerance):
                bad.append(f"{r['name']}: {label} {prev[key]} -> {r[key]} (+{100 * (r[key] / prev[key] - 1):.1f}%)")
        if prev["verified"] == "EQUIVALENT" and r["verified"] != "EQUIVALENT":
            bad.append(f"{r['name']}: verification regressed {prev['verified']} -> {r['verified']}")
    return bad


def format_table(rows: List[dict]) -> str:
    head = f"{'benchmark':<18}{'ANDs':>13}{'depth':>9}{'cells':>7}{'area':>9}{'WNS(ns)':>9}{'uW':>8}  {'verified':<14}{'s':>6}"
    out = [head, "-" * len(head)]
    for r in rows:
        out.append(f"{r['name']:<18}{str(r['ands_before']) + '->' + str(r['ands_after']):>13}"
                   f"{str(r['depth_before']) + '->' + str(r['depth_after']):>9}{r['cells']:>7}{r['area']:>9.1f}"
                   f"{r['wns']:>+9.3f}{r['power_uW']:>8.2f}  {r['verified']:<14}{r['seconds']:>6.1f}")
    return "\n".join(out)
