"""
Regression test for 4_self_improve_loop/evolution_orchestrator.py
Run: pytest tests/unit/test_orchestrator_baseline_wiring.py -v

Guards against a real bug found in this repo (2026-09): config's
`baseline_cells` / `baseline_depth` (auto-profiled per module, e.g. 1409/23
for picorv32_alu) were computed by run_self_learner.py but never actually
forwarded from EvolutionOrchestrator into fitness_evaluator.score() --
every module silently used the hardcoded alu_basic-sized defaults (40/6)
instead, which made the area/delay fitness signal nearly flat for any
larger real block and produced runs that looked like they weren't
evolving anything. This test fails loudly if that wiring regresses.
"""
import evolution_orchestrator as eo


def test_evaluate_one_forwards_config_baselines_and_timeouts(monkeypatch):
    captured = {}

    def fake_score(verilog_source, module_name, verilator_bin, yosys_bin,
                    baseline_cells, baseline_depth, sim_timeout, synth_timeout,
                    liberty_path=None, real_area_weight=0.25, baseline_real_area_um2=0.0):
        captured.update(dict(
            baseline_cells=baseline_cells, baseline_depth=baseline_depth,
            sim_timeout=sim_timeout, synth_timeout=synth_timeout,
        ))
        from fitness_evaluator import FitnessReport
        return FitnessReport(fitness=0.9, functionally_correct=True, pass_ratio=1.0,
                              cell_count=1300, logic_depth=20, sim_error="", synth_error="")

    monkeypatch.setattr(eo, "score", fake_score)
    monkeypatch.setattr(
        eo, "run_all_checks",
        lambda genome: type("DRC", (), {"passed": True, "violations": []})(),
    )

    config = {
        "module_name": "picorv32_alu",
        "baseline_cells": 1409,
        "baseline_depth": 23,
        "sim_timeout_sec": 90,
        "synth_timeout_sec": 90,
    }
    orch = eo.EvolutionOrchestrator(config)
    ind = eo.Individual(genome="module x; endmodule", generation=0)
    orch._evaluate_one(ind)

    assert captured["baseline_cells"] == 1409, (
        "baseline_cells from config was not forwarded to score() -- "
        "the fitness signal will silently fall back to the alu_basic-sized "
        "default (40) for every module, killing the area/delay gradient "
        "on larger real designs."
    )
    assert captured["baseline_depth"] == 23
    assert captured["sim_timeout"] == 90
    assert captured["synth_timeout"] == 90


def test_evaluate_one_falls_back_to_sane_defaults_when_config_omits_baselines():
    """alu_basic's config doesn't set baseline_cells/depth explicitly in some
    setups -- confirm the orchestrator still has a sane, non-crashing default
    rather than raising a KeyError."""
    orch = eo.EvolutionOrchestrator({"module_name": "alu_basic"})
    assert orch.baseline_cells == 40
    assert orch.baseline_depth == 6
