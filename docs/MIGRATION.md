# Updating your existing repo to this release (one step, covers ALL rounds, v5)

This zip (v5) is the **complete tree**, cumulative: it contains round 1 (the 8-gap fixes / new `evohdl/` package
layout), round 2 (A-H upgrades) and round 3 (sequential designs, syntax-tree parser + operators, automated formal
pipeline) and round 4 (native EDA kernel `evohdl/eda/`, `libs/`, formal-pipeline native fallback). round 5 (head-to-head harness, verified pre-pass emitter, wedge/customer docs). **Apply ONLY v5; do not apply v1-v4 first.** `docs/CHANGELOG_vs_original.md` lists every file that is new,
changed or removed relative to the repo you originally uploaded, so you can review it before copying.

1. Commit/stash anything you want to keep in your repo.
2. Copy everything from this zip over your repo root (overwrite). Your own `designs/seed/*.v`,
   `designs/best/*`, `dashboard/run_history_*.json` are not required by the new code; keep them if you like.
3. Remove what this release replaced:
   `bash scripts/cleanup_old_layout.sh --dry-run`, then `bash scripts/cleanup_old_layout.sh`
   (deletes only the old numbered folders `1_symbolic_core ... 4_self_improve_loop` and a few stale files).
4. `pip install -e .` (new `pyproject.toml`; makes `import evohdl` work), then `pytest tests/unit -v`.
5. Old commands changed: `python 2_evolutionary_engine/baseline_compare.py ...` ->
   `python -m evohdl.evolutionary_engine.baseline_compare ...` (same pattern for the other modules).
   `python run_self_learner.py --config ...` is unchanged.
6. Old config files keep working: every new key is optional. To keep the *old* search behaviour exactly,
   set `verification_mode: simulation`, `islands: 1`, `fitness_mode: legacy_ratio`.
7. Also run `python -m evohdl.sandbox.formal_pipeline --selftest` (8 real-Yosys cases: comb/counter/FSM/multiplier, each
   equivalent + deliberately broken). Send me any FAIL lines.
8. First thing to run on your WSL2 box (proves the generated Yosys scripts are valid with YOUR Yosys):
   `python -m evohdl.sandbox.equivalence_checker --selftest`
   Send me any FAIL lines.
9. Try the native flow (needs nothing installed): `python -m evohdl.eda bench run all` then `python -m evohdl.eda regress`
   (should print "no regressions vs previous run" against the shipped baseline DB).
10. The first real test of the business idea (needs Yosys + a real `.lib`):
    `LIB=<real.lib> bash scripts/run_head_to_head.sh` then read `benchmarks/reports/<run>/report.md` and `docs/WEDGE_PLAN.md` section 3.
