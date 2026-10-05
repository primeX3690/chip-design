"""
compare.py -- reproducible head-to-head benchmark harness (the evidence an investor / customer will ask for).

For every benchmark in a suite manifest it measures, on the SAME Liberty library (or iCE40 LUTs):

  baseline[flavor]          Yosys synth -flatten + abc (default script, and an area-oriented script)
  native                    this repo's own flow (elaborate -> optimize -> map), with proofs
  prepass+baseline[flavor]  OUR verified optimizer used as a pre-pass, emitted as Verilog with the original interface,
                            then fed through the SAME Yosys/abc flow  <-- the product wedge: "verified optimization on
                            top of the open-source flow"

and writes Markdown + JSON + CSV with environment fingerprints (tool versions, library/benchmark hashes, command line)
and an automatic "what this report does NOT show" section. Losses and unsupported designs are reported, never hidden.

Pre-pass scope (honest): combinational modules inside the native Verilog subset. Sequential designs get baseline and
native columns only (preserving original flops / async reset through an AIG round trip is future work).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from evohdl.eda.aig_verilog import aig_to_verilog, module_ports
from evohdl.eda.elaborate import elaborate
from evohdl.eda.flow import run_flow, verify
from evohdl.eda.liberty import Library, load_liberty
from evohdl.eda.opt import optimize
from evohdl.eda.techmap import techmap
from evohdl.paths import REPO_ROOT
from evohdl.sandbox.design_bundle import count_modules, load_design_bundle, looks_like_systemverilog
from evohdl.sandbox.equivalence_checker import is_sequential
from evohdl.sandbox.formal_pipeline import run_formal_pipeline
from evohdl.sandbox.process_guard import run_guarded
from evohdl.sandbox.yosys_synthesizer import LTP_RE, LTP_RE_LEGACY, parse_cell_count

FLAVORS: Dict[str, Optional[str]] = {
    "default": None,                                   # Yosys' own abc script for liberty mapping
    "area_strong": "+strash;dc2;dc2;dch -f;map -a",    # user-editable; an invalid script is reported as a failed flow
}
WIN_THRESHOLD = 0.005          # +-0.5% counts as a tie


# ---------------------------------------------------------------------------- environment fingerprint
def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def tool_version(binary: str, flag: str = "-V") -> str:
    if not shutil.which(binary):
        return "not installed"
    try:
        r = subprocess.run([binary, flag], capture_output=True, text=True, timeout=15)
        return ((r.stdout or r.stderr).strip().splitlines() or ["unknown"])[0][:120]
    except Exception:
        return "unknown"


def git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, timeout=10)
        return r.stdout.strip() or "n/a"
    except Exception:
        return "n/a"


# ---------------------------------------------------------------------------- yosys flows
@dataclass
class FlowResult:
    ok: bool
    area: float = 0.0          # um^2 (asic) or SB_LUT4 count (ice40)
    cells: int = 0
    depth: int = 0
    error: str = ""
    seconds: float = 0.0


AREA_RE = re.compile(r"Chip area for (?:top )?module '\\?([^']+)':\s*([-+0-9.eE]+)")
LUT_RE = re.compile(r"(?m)^\s*SB_LUT4\s+(\d+)\s*$|^\s*(\d+)\s+(?:[\d.]+\s+)?SB_LUT4\s*$")


def build_yosys_script(src_path: Path, top: str, lib_path: Optional[str], flavor: str, target: str,
                       sequential: bool, sv: bool, dont_use: List[str]) -> str:
    rd = "read_verilog -sv" if sv else "read_verilog"
    head = f"{rd} {src_path.as_posix()}\nhierarchy -check -top {top}\n"
    if target == "ice40":
        return head + f"synth_ice40 -top {top} -flatten\nstat\nltp -noff\n"
    script = FLAVORS.get(flavor)
    abc = f"abc -liberty {lib_path}" + "".join(f" -dont_use {d}" for d in dont_use) + (f" -script {script}" if script else "")
    return (head + f"synth -top {top} -flatten\n" + (f"dfflibmap -liberty {lib_path}\n" if sequential else "") +
            abc + f"\nopt_clean -purge\nstat -liberty {lib_path}\nltp -noff\n")


def parse_yosys_output(out: str, target: str) -> FlowResult:
    cells = parse_cell_count(out)
    if cells is None:
        return FlowResult(False, error="could not parse a cell count from Yosys `stat` output")
    m = LTP_RE.search(out) or LTP_RE_LEGACY.search(out)
    depth = int(m.group(1)) if m else 0
    if target == "ice40":
        luts = [int(a or b) for a, b in LUT_RE.findall(out)]
        return FlowResult(True, float(luts[-1]) if luts else 0.0, cells, depth)
    areas = AREA_RE.findall(out)
    if not areas:
        return FlowResult(False, error="no 'Chip area' line (is the Liberty file readable by Yosys?)")
    return FlowResult(True, float(areas[-1][1]), cells, depth)


def yosys_flow(source: str, top: str, lib_path: Optional[str], flavor: str, target: str, yosys_bin: str = "yosys",
               dont_use: Optional[List[str]] = None, timeout: float = 600.0) -> FlowResult:
    sv = looks_like_systemverilog(source)
    work = Path(tempfile.mkdtemp(prefix="evohdl_cmp_"))
    t0 = time.time()
    try:
        src = work / ("design.sv" if sv else "design.v")
        src.write_text(source)
        ys = work / "flow.ys"
        ys.write_text(build_yosys_script(src, top, lib_path, flavor, target, is_sequential(source), sv, dont_use or []))
        r = run_guarded([yosys_bin, "-Q", "-T", "-s", str(ys)], timeout_sec=timeout, cwd=str(work))
        if r.timed_out:
            return FlowResult(False, error=f"timeout after {timeout:.0f}s", seconds=time.time() - t0)
        if not r.ok:
            return FlowResult(False, error=((r.stderr or r.stdout)[-300:]).strip(), seconds=time.time() - t0)
        res = parse_yosys_output(r.stdout or "", target)
        res.seconds = round(time.time() - t0, 2)
        return res
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------- per benchmark
def evaluate_benchmark(b: dict, lib: Optional[Library], lib_path: Optional[str], target: str, flavors: List[str],
                       yosys_bin: str, have_yosys: bool, effort: int, out_dir: Path, dont_use: List[str]) -> dict:
    row: dict = {"name": b["name"], "family": b.get("family", ""), "top": b["top"], "errors": []}
    bun = load_design_bundle(b["files"], top=b["top"], root=REPO_ROOT)
    src = bun.source
    row["sequential"] = is_sequential(src)
    row["modules"] = count_modules(src)
    row["baseline"], row["prepass"] = {}, {}

    if have_yosys:
        for fl in flavors:
            r = yosys_flow(src, b["top"], lib_path, fl, target, yosys_bin, dont_use)
            row["baseline"][fl] = r.__dict__
            if not r.ok:
                row["errors"].append(f"baseline[{fl}]: {r.error[:160]}")

    # native flow ------------------------------------------------------------------
    aig = None
    try:
        aig = elaborate(src, b["top"])
    except Exception as e:  # noqa: BLE001
        row["native"] = {"supported": False, "reason": str(e)[:160]}
    if aig is not None and lib is not None and target == "asic":
        try:
            t0 = time.time()
            res = run_flow(aig, lib, b["top"], effort=effort, objective="area")
            unopt = techmap(aig.cleanup(), lib, "area", b["top"])
            row["native"] = {"supported": True, "ands_before": res["ands_before"], "ands_after": res["ands_after"],
                             "area": res["area"], "area_unmapped_opt": round(unopt.area(lib), 3), "cells": res["cells"],
                             "depth_before": res["depth_before"], "depth_after": res["depth_after"],
                             "verified": res["verified"], "wns": res["wns"], "seconds": round(time.time() - t0, 2)}
        except Exception as e:  # noqa: BLE001
            row["native"] = {"supported": True, "error": str(e)[:160]}
            row["errors"].append(f"native flow: {str(e)[:120]}")
    elif aig is not None:
        row["native"] = {"supported": True, "ands_before": aig.cleanup().num_ands()}

    # verified pre-pass (combinational only) ---------------------------------------
    if aig is not None and not aig.latches:
        pre: dict = {"applicable": True}
        try:
            before = aig.cleanup()
            opt = optimize(before, effort=effort)
            emitted = aig_to_verilog(opt, b["top"], module_ports(src, b["top"]))
            back = elaborate(emitted, b["top"])
            pre["ands_before"], pre["ands_after"] = before.num_ands(), opt.num_ands()
            pre["verify_native_cec"] = verify(before, opt).status
            pre["verify_roundtrip"] = verify(opt, back).status
            (out_dir / "prepass").mkdir(parents=True, exist_ok=True)
            (out_dir / "prepass" / f"{b['name']}.v").write_text(emitted)
            pre["verify_yosys_formal"] = "not run (Yosys missing)"
            if have_yosys:
                v = run_formal_pipeline(src, emitted, b["top"], yosys_bin=yosys_bin, use_native=False, timeout_sec=300)
                pre["verify_yosys_formal"] = v.status
            pre["flows"] = {}
            if have_yosys:
                for fl in flavors:
                    r = yosys_flow(emitted, b["top"], lib_path, fl, target, yosys_bin, dont_use)
                    pre["flows"][fl] = r.__dict__
                    if not r.ok:
                        row["errors"].append(f"prepass[{fl}]: {r.error[:160]}")
        except Exception as e:  # noqa: BLE001
            pre["error"] = str(e)[:200]
            row["errors"].append(f"prepass: {str(e)[:120]}")
        row["prepass"] = pre
    else:
        row["prepass"] = {"applicable": False,
                          "reason": "sequential design (flops/reset not preserved by the AIG round trip)" if aig is not None
                          else "outside the native Verilog subset"}
    return row


# ---------------------------------------------------------------------------- summary
def _ratio(new: Optional[float], base: Optional[float]) -> Optional[float]:
    return (new / base) if new is not None and base and base > 0 else None


def prepass_verified(pre: dict) -> bool:
    ok = pre.get("verify_native_cec") in ("EQUIVALENT", "SIM_ONLY") and pre.get("verify_roundtrip") in ("EQUIVALENT", "SIM_ONLY")
    y = pre.get("verify_yosys_formal", "")
    return ok and not y.startswith("NOT_EQUIVALENT")


def summarize(rows: List[dict], flavors: List[str]) -> dict:
    out: Dict[str, dict] = {}
    for fl in flavors:
        ratios, wins, ties, losses, skipped = [], [], [], [], []
        for r in rows:
            base = r["baseline"].get(fl)
            pre = r["prepass"].get("flows", {}).get(fl) if r["prepass"].get("applicable") else None
            if not base or not base.get("ok") or not pre or not pre.get("ok") or not prepass_verified(r["prepass"]):
                skipped.append(r["name"])
                continue
            q = _ratio(pre["area"], base["area"])
            if q is None:
                skipped.append(r["name"])
                continue
            ratios.append(q)
            (wins if q < 1 - WIN_THRESHOLD else losses if q > 1 + WIN_THRESHOLD else ties).append(r["name"])
        gm = math.exp(sum(math.log(q) for q in ratios) / len(ratios)) if ratios else None
        out[fl] = {"compared": len(ratios), "geomean_area_ratio": gm, "wins": wins, "ties": ties, "losses": losses,
                   "skipped": skipped}
    return out


# ---------------------------------------------------------------------------- report
def _fmt(v, nd=1) -> str:
    return "-" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def render_markdown(meta: dict, rows: List[dict], summary: dict, flavors: List[str]) -> str:
    unit = "LUT4" if meta["target"] == "ice40" else "um^2"
    L = [f"# Head-to-head benchmark report ({meta['date']})", ""]
    if meta["fictional_lib"]:
        L += ["> **WARNING: the Liberty library used is the bundled ILLUSTRATIVE `tiny_generic.lib` (fictional numbers). "
              "These areas are NOT silicon results. Re-run with a real PDK `.lib` before showing anyone.**", ""]
    if not meta["have_yosys"]:
        L += ["> **Yosys was not available: NO head-to-head result exists in this report** (native columns only).", ""]
    L += ["## Environment (reproducibility)", "", f"- command: `{meta['command']}`", f"- evohdl commit: `{meta['commit']}`",
          f"- yosys: `{meta['yosys']}`", f"- python: `{meta['python']}` on `{meta['platform']}`", f"- target: `{meta['target']}` "
          f"({'iCE40 LUT4 count' if meta['target'] == 'ice40' else 'Liberty area via stat -liberty'})",
          f"- library: `{meta['lib_name']}` sha256[:16] `{meta['lib_hash']}`", f"- abc flavors: {', '.join(f'`{f}`={FLAVORS.get(f) or 'yosys default'}' for f in flavors)}",
          f"- optimizer effort: {meta['effort']}", ""]
    L += ["## Results", "", f"Area unit: {unit}. `base` = Yosys flow on the original RTL; `pre` = same flow on our verified pre-pass output; "
          "`nat` = this repo's own flow. delta = pre vs base of the same flavor (negative = we are smaller).", ""]
    hdr = "| benchmark | kind | " + " | ".join(f"base[{f}] | pre[{f}] | delta[{f}]" for f in flavors) + " | native area | verified (pre-pass) | notes |"
    L += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
    for r in rows:
        cells = []
        for fl in flavors:
            b = r["baseline"].get(fl, {})
            p = r["prepass"].get("flows", {}).get(fl, {}) if r["prepass"].get("applicable") else {}
            bq = b.get("area") if b.get("ok") else None
            pq = p.get("area") if p.get("ok") else None
            q = _ratio(pq, bq)
            cells += [_fmt(bq), _fmt(pq), "-" if q is None else f"{100 * (q - 1):+.1f}%"]
        nat = r.get("native", {})
        pre = r["prepass"]
        ver = "n/a" if not pre.get("applicable") else (
            f"cec:{pre.get('verify_native_cec', '?')[:5]} rt:{pre.get('verify_roundtrip', '?')[:5]} yosys:{pre.get('verify_yosys_formal', '?')[:14]}")
        note = (nat.get("reason", "") if not nat.get("supported", True) else "") or ("; ".join(r["errors"])[:80])
        if not pre.get("applicable"):
            note = (note + " | " if note else "") + "pre-pass n/a: " + pre.get("reason", "")
        L.append(f"| {r['name']} | {'seq' if r['sequential'] else 'comb'} | " + " | ".join(cells) +
                 f" | {_fmt(nat.get('area'))} | {ver} | {note} |")
    L += ["", "## Summary (verified pre-pass only; each flavor compared to its own baseline)", ""]
    for fl in flavors:
        s = summary[fl]
        gm = s["geomean_area_ratio"]
        L.append(f"- **{fl}**: {s['compared']} designs compared; geomean area ratio "
                 f"{'n/a' if gm is None else f'{gm:.4f} ({100 * (gm - 1):+.2f}%)'}; wins {len(s['wins'])} {s['wins']}, "
                 f"ties {len(s['ties'])}, losses {len(s['losses'])} {s['losses']}; skipped {len(s['skipped'])}")
    L += ["", "## What this report does NOT show", ""]
    L += ["- Anything about silicon, timing closure, power or routability: only synthesized cell area and logic depth.",
          "- Results on designs larger or different from this suite; the suite is small and partly synthetic.",
          "- A pre-pass for sequential designs (not supported yet) or for designs outside the native Verilog subset.",
          "- Statistical significance: flows are deterministic, but ABC results can shift with input structure; "
          "a win of a few percent on one design is not a trend.",
          "- Independent verification of the elaborator/solver used for `verify_native_cec` (Yosys formal is the independent check; "
          "if it says 'not run', treat the equivalence as in-house only)."]
    if meta["have_yosys"] and all(not summary[f]["wins"] for f in flavors):
        L += ["", "**No wins were found on this suite. Do not claim an improvement.**"]
    return "\n".join(L) + "\n"


def write_outputs(out_dir: Path, meta: dict, rows: List[dict], summary: dict, flavors: List[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "report.md"
    md.write_text(render_markdown(meta, rows, summary, flavors))
    (out_dir / "results.json").write_text(json.dumps({"meta": meta, "rows": rows, "summary": summary}, indent=1, default=str))
    with open(out_dir / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["benchmark", "flavor", "base_area", "prepass_area", "delta_pct", "base_cells", "prepass_cells", "base_depth",
                    "prepass_depth", "verified", "native_area"])
        for r in rows:
            for fl in flavors:
                b = r["baseline"].get(fl, {})
                p = r["prepass"].get("flows", {}).get(fl, {}) if r["prepass"].get("applicable") else {}
                q = _ratio(p.get("area") if p.get("ok") else None, b.get("area") if b.get("ok") else None)
                w.writerow([r["name"], fl, b.get("area"), p.get("area"), None if q is None else round(100 * (q - 1), 3),
                            b.get("cells"), p.get("cells"), b.get("depth"), p.get("depth"),
                            prepass_verified(r["prepass"]) if r["prepass"].get("applicable") else "", r.get("native", {}).get("area")])
    return md


def run_suite(suite_path: Path, lib_path: Optional[str], out_dir: Path, target: str = "asic", flavors: Optional[List[str]] = None,
              yosys_bin: str = "yosys", effort: int = 2, dont_use: Optional[List[str]] = None, only: Optional[List[str]] = None,
              command: str = "", native_lib_max_mb: float = 8.0) -> dict:
    flavors = flavors or list(FLAVORS)
    suite = json.loads(Path(suite_path).read_text())
    lib_file = Path(lib_path) if lib_path else REPO_ROOT / "libs" / "tiny_generic.lib"
    fictional = lib_file.name == "tiny_generic.lib"
    lib = None
    size_mb = lib_file.stat().st_size / 1e6
    if size_mb > native_lib_max_mb:
        print(f"[compare] {lib_file.name} is {size_mb:.0f} MB > {native_lib_max_mb:.0f} MB: native (pure-Python) Liberty parsing "
              f"skipped; Yosys baselines and the verified pre-pass still run. Use --native-lib-max-mb to override.", file=sys.stderr)
    else:
        try:
            lib = load_liberty(lib_file)
        except Exception as e:  # noqa: BLE001 -- unsupported Liberty syntax: baseline still runs
            print(f"[compare] native Liberty parser could not read {lib_file.name}: {str(e)[:100]} (native columns disabled)", file=sys.stderr)
    have_yosys = bool(shutil.which(yosys_bin))
    rows = []
    for b in suite["benchmarks"]:
        if only and b["name"] not in only:
            continue
        print(f"[compare] {b['name']} ...", file=sys.stderr)
        rows.append(evaluate_benchmark(b, lib, str(lib_file), target, flavors, yosys_bin, have_yosys, effort, out_dir, dont_use or []))
    summary = summarize(rows, flavors)
    meta = {"date": time.strftime("%Y-%m-%d %H:%M"), "command": command or " ".join(sys.argv), "commit": git_commit(),
            "yosys": tool_version(yosys_bin), "python": sys.version.split()[0], "platform": platform.platform(),
            "target": target, "lib_name": lib_file.name, "lib_hash": sha256_file(lib_file), "fictional_lib": fictional,
            "have_yosys": have_yosys, "effort": effort,
            "suite_files": {b["name"]: [sha256_file(REPO_ROOT / f) for f in b["files"] if (REPO_ROOT / f).exists()] for b in suite["benchmarks"]}}
    md = write_outputs(out_dir, meta, rows, summary, flavors)
    return {"report": str(md), "summary": summary, "rows": rows, "meta": meta}
