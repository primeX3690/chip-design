"""Gap A/E (uncapped relative fitness) and C/G (formal verification path) -- tools mocked."""
from evohdl.evolutionary_engine import fitness_evaluator as fe
from evohdl.sandbox.equivalence_checker import EquivalenceOutcome


class _Sim:
    compiled = ran = True
    passed = total = 300
    pass_ratio = 1.0
    error = ""
    functionally_correct = True


def _synth(cells, depth):
    class S:
        synthesized = True
        cell_count = cells
        logic_depth = depth
        error = ""
    return S()


def _patch(monkeypatch, cells=1000, depth=20):
    monkeypatch.setattr(fe, "evaluate_design", lambda *a, **k: _Sim())
    monkeypatch.setattr(fe, "synthesize_design", lambda *a, **k: _synth(cells, depth))


def _score(**kw):
    return fe.score("module m; endmodule", module_name="m", baseline_cells=1000, baseline_depth=20, **kw)


def test_tie_is_exactly_one(monkeypatch):
    _patch(monkeypatch)
    assert _score().fitness == 1.0


def test_fifteen_percent_area_cut_is_rewarded_linearly(monkeypatch):
    _patch(monkeypatch, cells=850)
    r = _score()
    assert abs(r.fitness - 1.30) < 1e-9 and r.area_improvement_pct == 15.0


def test_no_saturation_more_reduction_always_scores_higher(monkeypatch):
    scores = []
    for cells in (1000, 900, 700, 400, 100):
        _patch(monkeypatch, cells=cells)
        scores.append(_score().fitness)
    assert scores == sorted(scores) and len(set(scores)) == len(scores)
    assert scores[-1] > 2.5  # far above the old "1.0" plateau


def test_worse_than_seed_is_floored_but_above_broken(monkeypatch):
    _patch(monkeypatch, cells=5000)
    assert _score().fitness == fe.CORRECT_BASE > fe.BROKEN_CEILING


def test_zero_depth_is_not_read_as_infinite_speedup(monkeypatch):
    _patch(monkeypatch, cells=1000, depth=0)
    assert _score().fitness == 1.0


def test_custom_weights_and_legacy_mode(monkeypatch):
    _patch(monkeypatch, cells=500)
    assert abs(_score(area_weight=1.0).fitness - 1.5) < 1e-9
    assert abs(_score(fitness_mode="legacy_ratio").fitness - (0.5 + 0.3 * 2 + 0.2 * 1)) < 1e-9


def test_formal_proof_skips_simulation(monkeypatch):
    _patch(monkeypatch, cells=900)
    monkeypatch.setattr(fe, "evaluate_design", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sim ran")))
    monkeypatch.setattr(fe, "check_equivalence_auto", lambda *a, **k: EquivalenceOutcome(checked=True, equivalent=True))
    r = _score(verification_mode="formal", seed_source="seed")
    assert r.functionally_correct and r.verified_by == "formal" and r.fitness > 1.0


def test_formal_counterexample_rejects_without_synthesis(monkeypatch):
    monkeypatch.setattr(fe, "synthesize_design", lambda *a, **k: (_ for _ in ()).throw(AssertionError("synth ran")))
    monkeypatch.setattr(fe, "check_equivalence_auto",
                        lambda *a, **k: EquivalenceOutcome(checked=True, equivalent=False, error="counterexample"))
    r = _score(verification_mode="hybrid", seed_source="seed")
    assert r.fitness == fe.NONEQUIV_FITNESS and not r.functionally_correct


def test_hybrid_inconclusive_falls_back_to_simulation(monkeypatch):
    _patch(monkeypatch, cells=1000)
    monkeypatch.setattr(fe, "check_equivalence_auto", lambda *a, **k: EquivalenceOutcome(checked=True, equivalent=False))
    r = _score(verification_mode="hybrid", seed_source="seed")
    assert r.functionally_correct and r.verified_by == "formal+simulation(fallback)"


def test_formal_mode_inconclusive_is_not_accepted(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(fe, "check_equivalence_auto", lambda *a, **k: EquivalenceOutcome(checked=True, equivalent=False))
    r = _score(verification_mode="formal", seed_source="seed")
    assert not r.functionally_correct and r.fitness == fe.UNPROVEN_FITNESS


def test_simulation_mode_never_calls_formal(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(fe, "check_equivalence_auto", lambda *a, **k: (_ for _ in ()).throw(AssertionError("formal ran")))
    assert _score(verification_mode="simulation", seed_source="seed").fitness == 1.0
