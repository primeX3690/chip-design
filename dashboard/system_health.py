"""
dashboard/system_health.py
------------------------------
CPU/RAM/simulation-queue status, importable by app.py as a sidebar panel or
runnable standalone for a quick CLI health check:

    python dashboard/system_health.py
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


@dataclass
class HealthSnapshot:
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float
    available: bool = True
    note: str = ""


def get_snapshot() -> HealthSnapshot:
    if not _HAS_PSUTIL:
        return HealthSnapshot(
            cpu_percent=0.0, ram_used_gb=0.0, ram_total_gb=0.0, ram_percent=0.0,
            available=False, note="psutil not installed -- run: pip install -r config/requirements.txt",
        )
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    return HealthSnapshot(
        cpu_percent=cpu,
        ram_used_gb=mem.used / (1024 ** 3),
        ram_total_gb=mem.total / (1024 ** 3),
        ram_percent=mem.percent,
    )


def render_streamlit_panel(st_module):
    """Call from dashboard/app.py: system_health.render_streamlit_panel(st)"""
    snap = get_snapshot()
    if not snap.available:
        st_module.warning(snap.note)
        return
    c1, c2 = st_module.columns(2)
    c1.metric("CPU", f"{snap.cpu_percent:.0f}%")
    c2.metric("RAM", f"{snap.ram_used_gb:.1f} / {snap.ram_total_gb:.1f} GB ({snap.ram_percent:.0f}%)")


if __name__ == "__main__":
    snap = get_snapshot()
    if snap.available:
        print(f"CPU: {snap.cpu_percent:.1f}%")
        print(f"RAM: {snap.ram_used_gb:.2f} / {snap.ram_total_gb:.2f} GB ({snap.ram_percent:.1f}%)")
    else:
        print(snap.note)
