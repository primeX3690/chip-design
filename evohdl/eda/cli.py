"""Command line for the native EDA kernel:  python -m evohdl.eda <command> ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evohdl.eda.aig import Aig
from evohdl.eda.bench_io import read_aag, read_bench, write_aag, write_bench
from evohdl.eda.benchmarks import BENCHMARKS
from evohdl.eda.cec import bmc_equiv, combinational_equiv, sequential_equiv_matched
from evohdl.eda.elaborate import elaborate
from evohdl.eda.flow import run_flow, verify
from evohdl.eda.liberty import load_liberty
from evohdl.eda.opt import optimize
from evohdl.eda.regress import connect, find_regressions, format_table, record
from evohdl.eda.sta import analyze, estimate_power, format_report, parse_sdc, Constraints
from evohdl.eda.techmap import techmap
from evohdl.paths import REPO_ROOT

DEFAULT_LIB = REPO_ROOT / "libs" / "tiny_generic.lib"
DEFAULT_DB = REPO_ROOT / "benchmarks" / "eda_regression.db"


def load_design(path: str, top: str | None = None) -> Aig:
    p = Path(path)
    if p.suffix == ".aag":
        return read_aag(p.read_text())
    if p.suffix == ".bench":
        return read_bench(p.read_text(), p.stem)
    if p.suffix in (".v", ".sv"):
        top = top or p.stem
        return elaborate(p.read_text(), top)
    raise SystemExit(f"unsupported input type: {p.suffix} (use .v .sv .aag .bench)")


def _lib(args):
    return load_liberty(args.lib)


def cmd_elab(a):
    g = load_design(a.input, a.top)
    print("AIG:", g.stats())
    if a.out:
        Path(a.out).write_text(write_aag(g) if a.out.endswith(".aag") else write_bench(g))
        print("wrote", a.out)


def cmd_opt(a):
    g = load_design(a.input, a.top)
    o = optimize(g, effort=a.effort, log=print)
    r = verify(g, o)
    print(f"ANDs {g.num_ands()} -> {o.num_ands()}, depth {g.depth()} -> {o.depth()}; equivalence: {r.status} ({r.method})")
    if a.out:
        Path(a.out).write_text(write_aag(o))
    return 0 if r.status != "NOT_EQUIVALENT" else 1


def cmd_map(a):
    g = optimize(load_design(a.input, a.top), effort=a.effort)
    lib = _lib(a)
    nl = techmap(g, lib, a.objective, a.top or Path(a.input).stem)
    print("netlist:", nl.stats(lib))
    if a.out:
        Path(a.out).write_text(nl.to_verilog(lib))
        print("wrote", a.out)


def cmd_sta(a):
    g = optimize(load_design(a.input, a.top), effort=a.effort)
    lib = _lib(a)
    nl = techmap(g, lib, a.objective, a.top or Path(a.input).stem)
    cons = parse_sdc(Path(a.sdc).read_text(), nl) if a.sdc else Constraints(period=a.period, clock_port=nl.clock)
    print(format_report(analyze(nl, lib, cons)))
    pw = estimate_power(nl, lib, cons)
    print(f"\npower @ {pw['freq_MHz']:.0f} MHz: dynamic {pw['dynamic_uW']:.3f} uW + leakage {pw['leakage_uW']:.3f} uW "
          f"(avg activity {pw['avg_activity']:.3f})")


def cmd_cec(a):
    x, y = load_design(a.a, a.top), load_design(a.b, a.top)
    r = verify(x, y, a.conflicts, a.bmc)
    print(f"{r.status} via {r.method}" + (f" -- {r.reason}" if r.reason else ""))
    if r.counterexample:
        print("counterexample:", dict(list(r.counterexample.items())[:24]))
    return 0 if r.status == "EQUIVALENT" else 1


def cmd_flow(a):
    g = load_design(a.input, a.top)
    sdc = Path(a.sdc).read_text() if a.sdc else None
    r = run_flow(g, _lib(a), a.top or Path(a.input).stem, a.effort, a.objective, a.period, sdc)
    print(format_table([r]))
    print(format_report(r["sta"]))
    if a.out:
        Path(a.out).write_text(r["netlist"].to_verilog(_lib(a)))
        print("wrote", a.out)
    return 0 if r["verified"] != "NOT_EQUIVALENT" else 1


def _run_set(names, a, lib):
    rows = []
    for n in names:
        rows.append(run_flow(BENCHMARKS[n].build(), lib, n, a.effort, a.objective, a.period))
    return rows


def cmd_bench(a):
    if a.action == "list":
        for b in BENCHMARKS.values():
            print(f"{b.name:<18}{b.family:<16}{b.note}")
        return 0
    if a.action == "run-dir":
        lib = _lib(a)
        rows = []
        for f in sorted(Path(a.target).glob("*")):
            if f.suffix in (".bench", ".aag"):
                rows.append(run_flow(load_design(str(f)), lib, f.stem, a.effort, a.objective, a.period))
        print(format_table(rows) if rows else f"no .bench/.aag files in {a.target}")
        return 0
    names = list(BENCHMARKS) if a.target in (None, "all") else [a.target]
    rows = _run_set(names, a, _lib(a))
    print(format_table(rows))
    return 1 if any(r["verified"] == "NOT_EQUIVALENT" for r in rows) else 0


def cmd_regress(a):
    lib = _lib(a)
    rows = _run_set(list(BENCHMARKS), a, lib)
    con = connect(a.db)
    bad = find_regressions(con, rows, a.objective, a.effort, a.tolerance)
    print(format_table(rows))
    if not a.no_record:
        record(con, rows, a.objective, a.effort)
        print(f"\nrecorded {len(rows)} runs in {a.db}")
    if bad:
        print("\nREGRESSIONS:\n  " + "\n  ".join(bad))
        return 1
    print("\nno regressions vs previous run")
    return 0


def cmd_compare(a):
    from evohdl.eda.compare import run_suite
    import time
    out = Path(a.out_dir) if a.out_dir else REPO_ROOT / "benchmarks" / "reports" / time.strftime("%Y%m%d-%H%M%S")
    res = run_suite(Path(a.suite), a.lib, out, a.target, a.flavor or None, a.yosys_bin, a.effort, a.dont_use, a.only,
                    command="python -m evohdl.eda compare " + " ".join(sys.argv[2:]),
                    native_lib_max_mb=a.native_lib_max_mb)
    print(f"report: {res['report']}")
    for fl, s in res["summary"].items():
        gm = s["geomean_area_ratio"]
        print(f"[{fl}] compared {s['compared']}  geomean area ratio {'n/a' if gm is None else f'{gm:.4f}'}  "
              f"wins {len(s['wins'])}  ties {len(s['ties'])}  losses {len(s['losses'])}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evohdl.eda", description="Native logic-level EDA kernel (no external tools).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, io=True):
        if io:
            p.add_argument("input")
        p.add_argument("--top")
        p.add_argument("--lib", default=str(DEFAULT_LIB))
        p.add_argument("--effort", type=int, default=2)
        p.add_argument("--objective", choices=["area", "delay"], default="area")
        p.add_argument("--period", type=float, default=2.0)
        p.add_argument("--sdc")
        p.add_argument("--out")

    for name, fn, h in (("elab", cmd_elab, "elaborate Verilog -> AIG (.aag/.bench out)"), ("opt", cmd_opt, "optimize + prove equivalent"),
                        ("map", cmd_map, "technology-map to a Liberty library"), ("sta", cmd_sta, "map, then STA + power"),
                        ("flow", cmd_flow, "optimize, map, verify, STA, power")):
        p = sub.add_parser(name, help=h)
        common(p)
        p.set_defaults(fn=fn)
    p = sub.add_parser("cec", help="prove two designs equivalent")
    p.add_argument("a"), p.add_argument("b"), p.add_argument("--top")
    p.add_argument("--conflicts", type=int, default=200000), p.add_argument("--bmc", type=int, default=8)
    p.set_defaults(fn=cmd_cec)
    p = sub.add_parser("bench", help="list / run benchmarks")
    p.add_argument("action", choices=["list", "run", "run-dir"])
    p.add_argument("target", nargs="?")
    common(p, io=False)
    p.set_defaults(fn=cmd_bench)
    p = sub.add_parser("compare", help="head-to-head vs Yosys+ABC on a suite (needs Yosys for the baseline)")
    p.add_argument("--suite", default=str(REPO_ROOT / "benchmarks" / "suite.json"))
    p.add_argument("--lib", default=str(DEFAULT_LIB), help="Liberty file for the area comparison (use a REAL .lib!)")
    p.add_argument("--target", choices=["asic", "ice40"], default="asic")
    p.add_argument("--flavor", action="append", help="abc flavor(s); default: all")
    p.add_argument("--yosys-bin", default="yosys")
    p.add_argument("--effort", type=int, default=2)
    p.add_argument("--dont-use", action="append", help="cell pattern passed to abc -dont_use (repeatable)")
    p.add_argument("--only", nargs="*", help="run only these benchmark names")
    p.add_argument("--out-dir")
    p.add_argument("--native-lib-max-mb", type=float, default=8.0,
                   help="skip native Liberty parsing above this size (the pure-Python parser is slow on full PDK libs)")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("regress", help="run all benchmarks, store in the regression DB, flag regressions")
    common(p, io=False)
    p.add_argument("--db", default=str(DEFAULT_DB)), p.add_argument("--tolerance", type=float, default=0.02)
    p.add_argument("--no-record", action="store_true")
    p.set_defaults(fn=cmd_regress)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
