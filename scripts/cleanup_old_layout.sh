#!/usr/bin/env bash
# Run ONCE, from the root of YOUR repo, AFTER copying this release's files over it.
# Removes only the files/folders this release replaced (old numbered folders, stale artifacts).
# Nothing else is touched. Review with --dry-run first:  bash scripts/cleanup_old_layout.sh --dry-run
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
OLD=(
  1_symbolic_core 2_evolutionary_engine 3_sandbox_time 4_self_improve_loop   # replaced by evohdl/
  tests/conftest.py                                                          # no longer needed (pyproject pythonpath)
  tests/unit/tese_design_rule_checker.py                                     # renamed test_design_rule_checker.py
  "designs/best/picorv32_alu_best (1).v" "designs/best/picorv32_alu_best_report (1).json"
  designs/best/counter_4bit_best.v designs/best/counter_4bit_best_report.json  # stale/broken
  benchmarks/gen12_snapshot.json benchmarks/gen12_snapshot.md benchmarks/gen26_snapshot.json benchmarks/gen26_snapshot.md
  benchmarks/gen32_snapshot.json benchmarks/gen32_snapshot.md benchmarks/report.md
  dashboard/run_history.json
)
[ -d evohdl ] || { echo "evohdl/ not found -- copy the new release into this repo first"; exit 1; }
for p in "${OLD[@]}"; do
  if [ -e "$p" ]; then
    if [ $DRY -eq 1 ]; then echo "would remove: $p"; else rm -rf "$p"; echo "removed: $p"; fi
  fi
done
find . -name __pycache__ -type d -prune -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
echo "done. Next: pip install -e . && pytest tests/unit -v"
