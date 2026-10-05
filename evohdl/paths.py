"""Single source of truth for repo-relative paths (designs/, config/, flow/ ...)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGNS_DIR = REPO_ROOT / "designs"
SEED_DIR = DESIGNS_DIR / "seed"
BEST_DIR = DESIGNS_DIR / "best"
CONFIG_DIR = REPO_ROOT / "config"
FLOW_DIR = REPO_ROOT / "flow"
