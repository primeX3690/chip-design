#!/usr/bin/env bash
# Reproducible head-to-head vs Yosys+ABC. Run on a machine WITH Yosys (WSL2/Linux). Not tested in the authoring sandbox
# (no Yosys there) -- the harness logic is unit-tested with a mocked Yosys; this script is the real run.
#
# usage:  LIB=/path/to/real_pdk.lib bash scripts/run_head_to_head.sh [asic|ice40]
# e.g.    LIB=$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib bash scripts/run_head_to_head.sh
set -euo pipefail
TARGET="${1:-asic}"
command -v yosys >/dev/null || { echo "yosys not found on PATH"; exit 2; }
if [ "$TARGET" = "asic" ] && [ -z "${LIB:-}" ]; then
  echo "Set LIB=/path/to/a/REAL .lib (the bundled tiny_generic.lib is fictional and the report will say so)."; fi
python -m evohdl.sandbox.formal_pipeline --selftest || { echo "formal selftest failed -- fix before trusting any comparison"; exit 1; }
OUT="benchmarks/reports/$(date +%Y%m%d-%H%M%S)"
ARGS=(--target "$TARGET" --out-dir "$OUT")
[ -n "${LIB:-}" ] && ARGS+=(--lib "$LIB")
# Add cells the flow must not use (edit for your PDK), e.g.:  DONT_USE="sky130_fd_sc_hd__probe_p_8 sky130_fd_sc_hd__probec_p_8"
for c in ${DONT_USE:-}; do ARGS+=(--dont-use "$c"); done
python -m evohdl.eda compare "${ARGS[@]}"
echo "Report: $OUT/report.md   (also results.csv / results.json / prepass/*.v)"
