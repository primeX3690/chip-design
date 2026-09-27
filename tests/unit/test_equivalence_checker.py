"""
tests/unit/test_equivalence_checker.py

Regression test for the Stage-4 addition (2026-09): formal SAT-based
equivalence checking (3_sandbox_time/equivalence_checker.py). This only
tests the *parsing/wiring* logic by mocking run_guarded's output with
real, verbatim strings Yosys is known to print, so it runs without a real
Yosys/SAT-solver install. It does NOT prove the yosys script itself is
correct end-to-end -- that needs a real Yosys run on the user's machine
(see the module's own `if __name__ == "__main__":` smoke test).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "3_sandbox_time"))

import equivalence_checker as ec  # noqa: E402
from process_guard import GuardedResult  # noqa: E402


def _mock_guarded(returncode: int, stdout: str, timed_out: bool = False):
    def fake_run_guarded(command, timeout_sec, cwd):
        return GuardedResult(command=command, returncode=returncode, stdout=stdout, timed_out=timed_out)
    return fake_run_guarded


def test_unsat_is_parsed_as_equivalent(monkeypatch):
    monkeypatch.setattr(ec, "run_guarded", _mock_guarded(
        0, "...\nSAT proof finished - no model found: SUCCESS!\n"))
    outcome = ec.check_equivalence("module x; endmodule", "module x; endmodule", module_name="x")
    assert outcome.checked is True
    assert outcome.equivalent is True
    assert outcome.inconclusive is False


def test_sat_counterexample_is_parsed_as_not_equivalent(monkeypatch):
    monkeypatch.setattr(ec, "run_guarded", _mock_guarded(
        0, "...\nSAT proof finished - model found: FAIL!\n"))
    outcome = ec.check_equivalence("module x; endmodule", "module y; endmodule", module_name="x")
    assert outcome.checked is True
    assert outcome.equivalent is False
    assert outcome.error  # a counterexample reason should be recorded


def test_unparseable_output_is_inconclusive_not_a_silent_pass(monkeypatch):
    """If Yosys's output format ever changes and neither regex matches,
    this must NOT silently report equivalent=True -- that would be worse
    than not checking at all."""
    monkeypatch.setattr(ec, "run_guarded", _mock_guarded(0, "some unrelated yosys log output\n"))
    outcome = ec.check_equivalence("module x; endmodule", "module x; endmodule", module_name="x")
    assert outcome.checked is True
    assert outcome.equivalent is False
    assert outcome.inconclusive is True


def test_timeout_is_reported_as_unchecked_with_error(monkeypatch):
    monkeypatch.setattr(ec, "run_guarded", _mock_guarded(1, "", timed_out=True))
    outcome = ec.check_equivalence("module x; endmodule", "module x; endmodule", module_name="x")
    assert outcome.checked is False
    assert "timeout" in outcome.error.lower()


def test_sequential_flag_is_recorded_as_bounded():
    """Sequential (bounded-cycle) results must be distinguishable from the
    unbounded combinational proof -- a caller (or pitch deck!) should never
    claim the stronger guarantee for the weaker check."""
    import equivalence_checker as ec2
    outcome = ec2.EquivalenceOutcome(checked=True, equivalent=True, bounded=True, seq_cycles=20)
    assert outcome.bounded is True
    assert outcome.seq_cycles == 20
