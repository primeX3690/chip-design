import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in [
    "1_symbolic_core",
    "2_evolutionary_engine",
    "3_sandbox_time",
    "4_self_improve_loop",
]:
    sys.path.append(str(ROOT / sub))
