"""python -m evohdl.doctor -- explains WHERE evohdl runs from, which tools it can see, and what the last GA run really did.

Typical confusion it resolves: `pip install -e .` points at ONE directory; every output (designs/best, dashboard/run_history.json,
benchmarks/...) is written relative to that directory, not to your current shell directory."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from evohdl.paths import REPO_ROOT


def _ver(binary: str, flag: str = "-V") -> str:
    p = shutil.which(binary)
    if not p:
        return "NOT FOUND"
    try:
        r = subprocess.run([binary, flag], capture_output=True, text=True, timeout=15)
        return f"{p}  ({((r.stdout or r.stderr).strip().splitlines() or ['?'])[0][:70]})"
    except Exception:
        return f"{p}  (version unknown)"


def inspect_history(path: Path) -> list:
    """Human-readable findings about dashboard/run_history.json."""
    notes = []
    if not path.exists():
        return [f"no run history at {path} (the GA has not completed a generation here)"]
    try:
        h = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        return [f"run history unreadable: {e}"]
    if not h:
        return ["run history is empty"]
    first, last = h[0], h[-1]
    age_h = (time.time() - path.stat().st_mtime) / 3600
    notes.append(f"{len(h)} generations recorded; file last modified {age_h:.1f} h ago")
    notes.append(f"generation {first.get('generation')}: best={first.get('best_fitness')}  ->  generation {last.get('generation')}: best={last.get('best_fitness')}")
    if all(float(x.get("best_fitness", 0)) == 0.0 for x in h):
        notes.append("EVERY candidate scored 0.0: nothing is being evaluated successfully. Usual causes: Verilator missing/failing to "
                     "compile the testbench, wrong module_name, or a seed that fails its own testbench. Run the GA and read the "
                     "first ERROR/WARNING lines.")
    elif abs(float(first.get("best_fitness", 0)) - 1.0) > 0.05 and first.get("generation") == 0:
        notes.append("generation 0 best is not ~1.0, but the seed itself should score ~1.0 under the default fitness: suspect a wrong "
                     "baseline (baseline_cells/baseline_depth) -- a high score may then be meaningless.")
    return notes


def main() -> int:
    print(f"python            : {sys.executable} ({sys.version.split()[0]})")
    import evohdl
    print(f"evohdl imported from: {Path(evohdl.__file__).resolve().parent}")
    print(f"REPO_ROOT (where ALL outputs are written): {REPO_ROOT}")
    print(f"current directory : {Path.cwd()}")
    if Path.cwd().resolve() != REPO_ROOT.resolve():
        print("  !! your shell is NOT in REPO_ROOT. Outputs (designs/best, dashboard/, benchmarks/) go to REPO_ROOT, so files in "
              "this directory may be OLD copies. Re-run `pip install -e .` from the directory you actually work in.")
    if str(REPO_ROOT).startswith("/mnt/"):
        print("  !! REPO_ROOT is on the Windows drive (/mnt/...): very slow in WSL2 and can break file locking. Prefer ~/chip.")
    print("\ntools:")
    for name, flag in (("yosys", "-V"), ("verilator", "--version"), ("eqy", "--version"), ("sby", "--version"),
                       ("nextpnr-ice40", "--version"), ("iverilog", "-V"), ("g++", "--version")):
        print(f"  {name:<14} {_ver(name, flag)}")
    print("\nlast GA run:")
    for n in inspect_history(REPO_ROOT / "dashboard" / "run_history.json"):
        print(f"  - {n}")
    rep = REPO_ROOT / "designs" / "best"
    if rep.exists():
        for f in sorted(rep.glob("*_best_report.json")):
            try:
                d = json.loads(f.read_text())
                flag = "  <-- old-format report (no verified_by): produced by an old version" if "verified_by" not in d else ""
                print(f"  {f.name}: fitness={d.get('fitness')} cells={d.get('cell_count')} depth={d.get('logic_depth')} "
                      f"correct={d.get('functionally_correct')} verified_by={d.get('verified_by', 'n/a')}{flag}")
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
