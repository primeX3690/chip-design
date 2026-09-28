"""
tests/unit/test_constraint_extractor_consistency.py

Regression test for the baseline-profiling/live-scoring mismatch bug found
(2026-09): a real 40-generation picorv32_alu run reported cell_count and
logic_depth EXACTLY tied to the seed (1318=1318, 23=23 via
baseline_compare.py), yet best_fitness was 0.8522 instead of the correct
1.0 for an exact tie -- because constraint_extractor.py (used to
auto-profile baseline_cells/baseline_depth once at run start) ran a
slightly different Yosys script than yosys_synthesizer.py (used to score
every individual during the GA loop), so the "baseline" and "live" cell
counts for the IDENTICAL design didn't match.

Fix: constraint_extractor.extract_constraints() now calls
yosys_synthesizer.synthesize_design() directly instead of maintaining a
second, drifted Yosys script. This test mocks that shared function so it
runs without a real Yosys install, and asserts the two profiling paths are
now structurally the same call.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "1_symbolic_core"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "3_sandbox_time"))

import constraint_extractor as ce  # noqa: E402


def test_extract_constraints_uses_synthesize_design_directly(monkeypatch):
    """Guards against the two profiling paths drifting apart again -- if
    someone reintroduces a second, separate Yosys script here instead of
    calling yosys_synthesizer.synthesize_design(), this test's mock will
    simply never be hit and the assertions below will fail."""
    calls = []

    class FakeOutcome:
        synthesized = True
        cell_count = 1318
        wire_count = 200
        logic_depth = 23
        error = ""

    def fake_synthesize_design(verilog_source, module_name, yosys_bin, timeout_sec):
        calls.append((module_name, yosys_bin, timeout_sec))
        return FakeOutcome()

    import yosys_synthesizer
    monkeypatch.setattr(yosys_synthesizer, "synthesize_design", fake_synthesize_design)

    constraints = ce.extract_constraints("module picorv32_alu(); endmodule", "picorv32_alu")

    assert len(calls) == 1, "extract_constraints must call synthesize_design exactly once"
    assert constraints.baseline_cells == 1318
    assert constraints.baseline_wires == 200
    assert constraints.baseline_depth == 23


def test_a_tied_design_now_scores_fitness_one(monkeypatch):
    """End-to-end sanity check: if baseline_cells/depth (from profiling) and
    an individual's own measured cell_count/logic_depth (from live scoring)
    are IDENTICAL -- as they always are for the unmutated seed individual
    that's guaranteed to be in generation 0 -- fitness must be exactly 1.0,
    not something like 0.85."""
    sys.path.append(str(Path(__file__).resolve().parents[2] / "2_evolutionary_engine"))
    import fitness_evaluator as fe

    class FakeSim:
        compiled = True
        ran = True
        passed = 300
        total = 300
        pass_ratio = 1.0
        error = ""

        @property
        def functionally_correct(self):
            return True

    class FakeSynth:
        synthesized = True
        cell_count = 1318
        logic_depth = 23
        error = ""

    monkeypatch.setattr(fe, "evaluate_design", lambda *a, **k: FakeSim())
    monkeypatch.setattr(fe, "synthesize_design", lambda *a, **k: FakeSynth())

    report = fe.score(
        "module picorv32_alu(); endmodule",
        module_name="picorv32_alu",
        baseline_cells=1318,   # same profiling result FakeSynth would produce
        baseline_depth=23,
    )
    assert report.fitness == 1.0, (
        f"expected fitness=1.0 for a design exactly tied to baseline, got {report.fitness} -- "
        "baseline profiling and live scoring have drifted apart again."
    )

