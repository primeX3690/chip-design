"""
tests/unit/test_tech_aware_synthesizer.py

Regression test for the Stage-5 addition (2026-09): real standard-cell-
library-mapped synthesis (3_sandbox_time/tech_aware_synthesizer.py). Only
tests the parsing/wiring logic via mocked Yosys `stat -liberty` output
(real, verbatim format Yosys is known to print) -- does not need a real
.lib file or Yosys install. See the module's own `__main__` block for a
real smoke test against an actual sky130 liberty file.
"""
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "3_sandbox_time"))

import tech_aware_synthesizer as tas  # noqa: E402
from process_guard import GuardedResult  # noqa: E402

REAL_STAT_LIBERTY_OUTPUT = """
=== picorv32_alu ===

   Number of wires:                 42
   Number of wire bits:            512
   Number of cells:                 87
     sky130_fd_sc_hd__and2_1        12
     sky130_fd_sc_hd__xor2_1         8

   Chip area for module '\\picorv32_alu': 1318.451200
"""


def _mock_guarded(returncode: int, stdout: str, timed_out: bool = False):
    def fake_run_guarded(command, timeout_sec, cwd):
        return GuardedResult(command=command, returncode=returncode, stdout=stdout, timed_out=timed_out)
    return fake_run_guarded


def _fake_lib_file() -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".lib", delete=False)
    f.write("library(fake) { }")
    f.close()
    return f.name


def test_liberty_available_false_when_missing():
    assert tas.liberty_available(None) is False
    assert tas.liberty_available("/does/not/exist.lib") is False


def test_liberty_available_true_for_real_file():
    path = _fake_lib_file()
    assert tas.liberty_available(path) is True


def test_parses_real_area_from_stat_liberty_output(monkeypatch):
    monkeypatch.setattr(tas, "run_guarded", _mock_guarded(0, REAL_STAT_LIBERTY_OUTPUT))
    lib = _fake_lib_file()
    outcome = tas.synthesize_tech_mapped("module x; endmodule", "picorv32_alu", lib)
    assert outcome.synthesized is True
    assert outcome.real_area_um2 == 1318.4512
    assert outcome.cell_count == 87


def test_missing_area_line_is_reported_as_failure_not_zero(monkeypatch):
    """If Yosys's output format ever changes, this must NOT silently report
    a real_area_um2 of 0.0 -- that would look like an implausibly perfect
    design instead of a parsing failure."""
    monkeypatch.setattr(tas, "run_guarded", _mock_guarded(0, "some unrelated yosys log\n"))
    lib = _fake_lib_file()
    outcome = tas.synthesize_tech_mapped("module x; endmodule", "picorv32_alu", lib)
    assert outcome.synthesized is False
    assert outcome.real_area_um2 == 0.0
    assert "Chip area" in outcome.error or "no 'Chip area" in outcome.error


def test_missing_liberty_file_fails_fast_without_running_yosys(monkeypatch):
    calls = []
    monkeypatch.setattr(tas, "run_guarded", lambda *a, **k: calls.append(1))
    outcome = tas.synthesize_tech_mapped("module x; endmodule", "x", "/does/not/exist.lib")
    assert outcome.synthesized is False
    assert calls == [], "should never shell out to Yosys when the .lib path doesn't exist"
