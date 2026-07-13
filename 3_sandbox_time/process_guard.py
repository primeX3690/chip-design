"""
process_guard.py
-----------------
Safe subprocess execution wrapper used by every module that shells out to
Verilator / Yosys. Enforces wall-clock timeout and (on POSIX) a memory
ceiling via `resource`, so a single bad genome (e.g. an infinite
combinational loop) can never hang or crash the evolutionary loop.
"""

from __future__ import annotations

import subprocess
import time
import os
import signal
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("EvoHDL.process_guard")

try:
    import resource  # POSIX only
    _HAS_RESOURCE = True
except ImportError:  # pragma: no cover - Windows fallback
    _HAS_RESOURCE = False


@dataclass
class GuardedResult:
    """Uniform result object returned by run_guarded()."""
    command: List[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_sec: float = 0.0
    ok: bool = field(init=False)

    def __post_init__(self):
        self.ok = (self.returncode == 0) and not self.timed_out


def _limit_memory(mem_limit_mb: int):
    """preexec_fn target: caps the child process's address space (Linux/macOS)."""
    if not _HAS_RESOURCE:
        return
    try:
        mem_bytes = mem_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except (ValueError, resource.error):
        # Some sandboxes disallow RLIMIT_AS changes; degrade gracefully.
        pass


def run_guarded(
    command: List[str],
    timeout_sec: float = 15.0,
    mem_limit_mb: int = 1024,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
) -> GuardedResult:
    """
    Run `command` with a wall-clock timeout and a soft memory cap.
    Never raises for tool-level failures (non-zero exit, timeout) -- those
    are reported in the returned GuardedResult so callers can score fitness
    as 0 instead of crashing the whole generation.
    """
    start = time.monotonic()
    preexec = (lambda: _limit_memory(mem_limit_mb)) if os.name == "posix" else None

    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            preexec_fn=preexec,
        )
        duration = time.monotonic() - start
        return GuardedResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            timed_out=False,
            duration_sec=duration,
        )
    except subprocess.TimeoutExpired as e:
        duration = time.monotonic() - start
        logger.warning("Command timed out after %.2fs: %s", duration, " ".join(command))
        return GuardedResult(
            command=command,
            returncode=-1,
            stdout=e.stdout or "" if isinstance(e.stdout, str) else "",
            stderr=(e.stderr or "") if isinstance(e.stderr, str) else "" + "\n[EvoHDL] process killed: timeout",
            timed_out=True,
            duration_sec=duration,
        )
    except FileNotFoundError:
        logger.error("Executable not found: %s", command[0])
        return GuardedResult(
            command=command,
            returncode=-2,
            stderr=f"[EvoHDL] executable '{command[0]}' not found on PATH. "
                   f"Install it and check config/system_config.yaml tool paths.",
            timed_out=False,
            duration_sec=time.monotonic() - start,
        )
    except Exception as e:  # noqa: BLE001 - last line of defense for the GA loop
        logger.exception("Unexpected error running command")
        return GuardedResult(
            command=command,
            returncode=-3,
            stderr=f"[EvoHDL] unexpected error: {e}",
            timed_out=False,
            duration_sec=time.monotonic() - start,
        )
