import json
import time

from evohdl import doctor


def test_all_zero_history_is_diagnosed(tmp_path):
    p = tmp_path / "run_history.json"
    p.write_text(json.dumps([{"generation": 0, "best_fitness": 0.0}, {"generation": 1, "best_fitness": 0.0}]))
    notes = doctor.inspect_history(p)
    assert any("EVERY candidate scored 0.0" in n for n in notes)


def test_suspicious_generation_zero_score_is_flagged_and_healthy_run_is_quiet(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps([{"generation": 0, "best_fitness": 2.4}, {"generation": 1, "best_fitness": 2.6}]))
    assert any("wrong baseline" in n for n in doctor.inspect_history(p))
    p.write_text(json.dumps([{"generation": 0, "best_fitness": 1.0}, {"generation": 5, "best_fitness": 1.12}]))
    notes = doctor.inspect_history(p)
    assert not any("EVERY" in n or "wrong baseline" in n for n in notes)
    assert doctor.inspect_history(tmp_path / "missing.json")[0].startswith("no run history")


def test_doctor_main_runs():
    assert doctor.main() == 0
