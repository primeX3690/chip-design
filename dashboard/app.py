"""
dashboard/app.py
--------------------
Streamlit monitoring dashboard.

Run with:  streamlit run dashboard/app.py

Reads dashboard/run_history.json (written incrementally by
evolution_orchestrator.py) and designs/best/*_best.v, so it can be left
open in a browser tab while run_self_learner.py runs in another terminal --
just hit "Refresh" or enable auto-refresh.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import sys

sys.path.append(str(Path(__file__).resolve().parent))
import system_health  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
BEST_DIR = PROJECT_ROOT / "designs" / "best"

st.set_page_config(page_title="EvoHDL Dashboard", layout="wide")
st.title("EvoHDL — Self-Improving RTL Optimization")
st.caption("Live view of the evolutionary loop's fitness, diversity, and best-of-run Verilog design.")


def discover_history_files() -> list[Path]:
    """Per-module run_history_<module>.json files (see evolution_orchestrator.py),
    plus the legacy single run_history.json for backward compatibility with
    older runs that predate the per-module fix."""
    per_module = sorted(DASHBOARD_DIR.glob("run_history_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    legacy = DASHBOARD_DIR / "run_history.json"
    if legacy.exists():
        per_module.append(legacy)
    return per_module


def load_history(history_path: Path) -> pd.DataFrame:
    if not history_path.exists():
        return pd.DataFrame()
    try:
        data = json.loads(history_path.read_text())
    except json.JSONDecodeError:
        return pd.DataFrame()
    return pd.DataFrame(data)


def load_best_design(module_name: str = "alu_basic") -> tuple[str, dict]:
    design_path = BEST_DIR / f"{module_name}_best.v"
    report_path = BEST_DIR / f"{module_name}_best_report.json"
    source = design_path.read_text() if design_path.exists() else "// No best design yet -- run run_self_learner.py first."
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    return source, report


with st.sidebar:
    st.header("Controls")
    module_name = st.text_input("Module name", value="alu_basic")
    auto_refresh = st.checkbox("Auto-refresh (5s)", value=False)
    if st.button("Refresh now"):
        st.rerun()
    st.divider()
    st.subheader("System health")
    system_health.render_streamlit_panel(st)

df = load_history(DASHBOARD_DIR / f"run_history_{module_name}.json"
                   if (DASHBOARD_DIR / f"run_history_{module_name}.json").exists()
                   else DASHBOARD_DIR / "run_history.json")  # legacy fallback

if df.empty:
    st.info("No run history yet. Start a run with:  `python run_self_learner.py`")
else:
    latest = df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Generation", int(latest["generation"]))
    col2.metric("Best fitness", f"{latest['best_fitness']:.4f}")
    col3.metric("Avg fitness", f"{latest['avg_fitness']:.4f}")
    col4.metric("Diversity", f"{latest['diversity']:.2f}")

    st.subheader("Fitness over generations")
    st.line_chart(df.set_index("generation")[["best_fitness", "avg_fitness", "worst_fitness"]])

    st.subheader("Population diversity over generations")
    st.line_chart(df.set_index("generation")[["diversity"]])

st.subheader("Current best design")
source, report = load_best_design(module_name)
col_a, col_b = st.columns([2, 1])
with col_a:
    st.code(source, language="verilog")
with col_b:
    st.markdown("**Fitness report**")
    if report:
        st.json(report)
    else:
        st.write("No report yet.")

if auto_refresh:
    time.sleep(5)
    st.rerun()

