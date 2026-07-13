"""
verilator_sandbox.py
---------------------
Runs a candidate Verilog design through Verilator:
  1. Lint + compile the design + C++ testbench into a native sim binary.
  2. Execute the binary.
  3. Parse "EVOHDL_RESULT passed=X total=Y" from stdout.

Everything happens inside a throwaway temp directory per evaluation so
parallel generations never collide on build artifacts.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from process_guard import run_guarded, GuardedResult  # noqa: E402

sys.path.append(str(Path(__file__).resolve().parent.parent / "3_sandbox_time"))
from testbench_generator import write_testbench  # noqa: E402

logger = logging.getLogger("EvoHDL.verilator_sandbox")

RESULT_RE = re.compile(r"EVOHDL_RESULT\s+passed=(\d+)\s+total=(\d+)")


@dataclass
class SimulationOutcome:
    compiled: bool
    ran: bool
    passed: int = 0
    total: int = 0
    pass_ratio: float = 0.0
    log: str = ""
    error: str = ""

    @property
    def functionally_correct(self) -> bool:
        return self.compiled and self.ran and self.total > 0 and self.passed == self.total


def evaluate_design(
    verilog_source: str,
    module_name: str = "alu_basic",
    verilator_bin: str = "verilator",
    timeout_sec: float = 20.0,
    num_random_vectors: int = 200,
    keep_workdir: bool = False,
) -> SimulationOutcome:
    """
    Compile + simulate one Verilog genome. Never raises: all failure modes
    (syntax error, timeout, mismatch) collapse into a SimulationOutcome with
    pass_ratio reflecting how "alive" the design is, so the GA can still
    rank a partially-broken genome against a totally-broken one.
    """
    workdir = Path(tempfile.mkdtemp(prefix="evohdl_sim_"))
    try:
        design_path = workdir / f"{module_name}.v"
        design_path.write_text(verilog_source)

        tb_path = workdir / f"tb_{module_name}.cpp"
        write_testbench(module_name, tb_path, num_random_vectors=num_random_vectors)

        obj_dir = workdir / "obj_dir"

        # Step 1: verilate + build native sim binary in one shot (--build --exe)
        compile_cmd = [
            verilator_bin,
            "--cc", "--exe", "--build",
            "-Wno-fatal",
            "-Wno-lint",
            "--Mdir", str(obj_dir),
            "-o", "sim.out",
            str(design_path),
            str(tb_path),
        ]
        compile_result: GuardedResult = run_guarded(
            compile_cmd, timeout_sec=timeout_sec, cwd=str(workdir)
        )

        if not compile_result.ok:
            reason = "timeout" if compile_result.timed_out else "compile error"
            return SimulationOutcome(
                compiled=False,
                ran=False,
                log=compile_result.stdout,
                error=f"[{reason}] {compile_result.stderr[-2000:]}",
            )

        sim_binary = obj_dir / "sim.out"
        if not sim_binary.exists():
            # Verilator puts the binary in Mdir by default with --build
            candidates = list(obj_dir.glob("sim.out")) + list(obj_dir.glob("*.out"))
            if candidates:
                sim_binary = candidates[0]
            else:
                return SimulationOutcome(
                    compiled=False, ran=False,
                    error="verilator reported success but no sim binary was produced",
                    log=compile_result.stdout,
                )

        # Step 2: run the simulation
        run_result: GuardedResult = run_guarded(
            [str(sim_binary)], timeout_sec=timeout_sec, cwd=str(workdir)
        )

        combined_out = run_result.stdout + "\n" + run_result.stderr
        match = RESULT_RE.search(combined_out)

        if run_result.timed_out:
            return SimulationOutcome(
                compiled=True, ran=False,
                error="simulation timed out (possible combinational loop / infinite latch)",
                log=combined_out[-2000:],
            )

        if not match:
            return SimulationOutcome(
                compiled=True, ran=False,
                error="simulation ran but produced no parseable result line",
                log=combined_out[-2000:],
            )

        passed, total = int(match.group(1)), int(match.group(2))
        ratio = passed / total if total else 0.0
        return SimulationOutcome(
            compiled=True, ran=True,
            passed=passed, total=total, pass_ratio=ratio,
            log=combined_out[-2000:],
        )

    finally:
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            logger.info("Kept sandbox workdir at %s", workdir)


if __name__ == "__main__":
    demo_source = Path(__file__).resolve().parent.parent / "designs" / "seed" / "alu_basic.v"
    if demo_source.exists():
        outcome = evaluate_design(demo_source.read_text())
        print(outcome)
    else:
        print("Seed design not found for smoke test.")
