"""Orchestrator wiring for islands (D), eval cache (G), verification modes (C), hierarchical seeds (H)."""
import yaml
from pathlib import Path

from evohdl.self_improve_loop import evolution_orchestrator as eo
from evohdl.evolutionary_engine.fitness_evaluator import FitnessReport
from evohdl.paths import REPO_ROOT


def _rep(f, cells=100):
    return FitnessReport(fitness=f, functionally_correct=True, pass_ratio=1.0, cell_count=cells, logic_depth=3,
                         sim_error="", synth_error="")


def _cfg(**kw):
    base = yaml.safe_load((REPO_ROOT / "config" / "system_config.yaml").read_text())
    base.update(generations=4, population_size=12, max_parallel_evals=1, auto_baseline=False)
    base.update(kw)
    return base


def _isolate(monkeypatch, tmp_path, calls):
    def fake_score(src, **kw):
        calls.append((len(src), kw))
        return _rep(1.0 + (len(src) % 17) / 10.0)
    monkeypatch.setattr(eo, "score", fake_score)
    monkeypatch.setattr(eo, "export_pareto_front_csv", lambda *a, **k: None)
    monkeypatch.setattr(eo, "mutate", lambda g, rng, operator_weights=None: (g + f"\n// m{rng.randint(0, 5)}",
                                                                           type("M", (), {"kind": "operator_swap"})()))
    monkeypatch.setattr(eo, "configure_resynth", lambda *a, **k: None)
    from evohdl.self_improve_loop import design_generator as dg
    monkeypatch.setattr(dg, "mutate", lambda g, rng, operator_weights=None: (g + f"\n// init{rng.randint(0, 9)}", None))


def _make(monkeypatch, tmp_path, **cfg):
    calls = []
    _isolate(monkeypatch, tmp_path, calls)
    orch = eo.EvolutionOrchestrator(_cfg(**cfg))
    orch.designs_dir = tmp_path / "designs"
    orch.log_path = tmp_path / "history.json"
    return orch, calls


def test_island_run_keeps_islands_separate_and_migrates(monkeypatch, tmp_path):
    orch, _ = _make(monkeypatch, tmp_path, islands=3, migration_interval=2, migration_count=1)
    best = orch.run()
    assert best.fitness_report is not None
    assert len(orch.island_model) == 3 and sum(len(i.population) for i in orch.island_model.islands) == 12
    assert orch.island_model.migrations_done >= 0
    hist = orch.history[-1]
    assert len(hist["island_best_fitness"]) == 3 and "migrations_total" in hist
    # union view == all islands
    assert len(orch.pool.population) == 12


def test_single_island_default_is_unchanged(monkeypatch, tmp_path):
    orch, _ = _make(monkeypatch, tmp_path, islands=1)
    assert orch.island_model is None
    orch.run()
    assert "island_best_fitness" not in orch.history[-1]


def test_duplicate_genomes_are_evaluated_once(monkeypatch, tmp_path):
    orch, calls = _make(monkeypatch, tmp_path, population_size=8, generations=1)
    orch.bootstrap()
    orch.pool.population = [eo.Individual(genome="module x; endmodule", generation=0) for _ in range(8)]
    orch.evaluate_population()
    assert len(calls) == 1 and orch.cache_hits == 7
    assert all(i.fitness_report is not None for i in orch.pool.population)
    # a second population containing the same genome costs nothing
    orch.pool.population = [eo.Individual(genome="module x; endmodule", generation=1) for _ in range(5)]
    orch.evaluate_population()
    assert len(calls) == 1


def test_new_scoring_options_are_forwarded(monkeypatch, tmp_path):
    orch, calls = _make(monkeypatch, tmp_path, verification_mode="hybrid", fitness_mode="relative_gain",
                        area_weight=3.0, equiv_timeout_sec=12, generations=1, population_size=4)
    orch.run()
    kw = calls[0][1]
    assert kw["verification_mode"] == "hybrid" and kw["area_weight"] == 3.0 and kw["equiv_timeout"] == 12
    assert kw["seed_source"] and "module alu_basic" in kw["seed_source"]


def test_unregistered_module_switches_to_formal(monkeypatch, tmp_path):
    cfg = dict(seed_files=["designs/examples/hier_mac/adder8.sv", "designs/examples/hier_mac/mult4.sv",
                           "designs/examples/hier_mac/mac_top.sv"],
               module_name="mac_top", generations=1, population_size=4, verification_mode="hybrid", islands=1)
    orch, calls = _make(monkeypatch, tmp_path, **cfg)
    cfg_base = orch.config
    cfg_base.pop("seed_design", None)
    orch.run()
    assert orch.verification_mode == "formal"
    assert "module mac_top" in orch.seed_source and "module adder8" in orch.seed_source
    assert (tmp_path / "designs" / "best" / "mac_top_seed_flat.v").exists()
    assert calls[0][1]["verification_mode"] == "formal"
