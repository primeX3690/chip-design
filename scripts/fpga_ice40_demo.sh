#!/usr/bin/env bash
# FPGA proof-of-concept: the same design through plain Yosys vs through our verified pre-pass, on iCE40, then place&route.
# Needs: yosys, nextpnr-ice40, icepack (+ iceprog and a board to actually load it). NOT run in the authoring sandbox.
#
# usage: bash scripts/fpga_ice40_demo.sh DESIGN.v TOP PINS.pcf [--up5k --package sg48 --freq 12]
# (pick the --device/--package/--pcf for YOUR board; the defaults below are only an example for an UP5K board)
set -euo pipefail
V="$1"; TOP="$2"; PCF="$3"; shift 3
FREQ=12; DEV=--up5k; PKG=sg48
mkdir -p build/fpga
# 1) original
yosys -q -p "read_verilog $V; synth_ice40 -top $TOP -flatten -json build/fpga/orig.json; tee -o build/fpga/orig.stat stat"
# 2) verified pre-pass (combinational modules only), emitted with the original interface
python - <<PY
from pathlib import Path
from evohdl.eda.elaborate import elaborate
from evohdl.eda.opt import optimize
from evohdl.eda.aig_verilog import aig_to_verilog, module_ports
from evohdl.eda.flow import verify
src = Path("$V").read_text(); g = elaborate(src, "$TOP").cleanup(); o = optimize(g)
r = verify(g, o); print("native equivalence:", r.status, r.method)
assert r.status in ("EQUIVALENT", "SIM_ONLY"), "refusing to continue: not equivalent"
Path("build/fpga/prepass.v").write_text(aig_to_verilog(o, "$TOP", module_ports(src, "$TOP")))
PY
python -m evohdl.sandbox.formal_pipeline --seed "$V" --evolved build/fpga/prepass.v --module "$TOP" --out-dir build/fpga
yosys -q -p "read_verilog build/fpga/prepass.v; synth_ice40 -top $TOP -flatten -json build/fpga/pre.json; tee -o build/fpga/pre.stat stat"
for v in orig pre; do
  echo "== $v =="; grep -E "SB_LUT4|SB_CARRY|SB_DFF" build/fpga/$v.stat || true
  nextpnr-ice40 $DEV --package $PKG --json build/fpga/$v.json --pcf "$PCF" --freq $FREQ --asc build/fpga/$v.asc 2>&1 | grep -E "Max frequency|Info: .*LUT|ICESTORM_LC" | tail -4
  icepack build/fpga/$v.asc build/fpga/$v.bin
done
echo "Load with: iceprog build/fpga/pre.bin   (and orig.bin) -- then measure on the board"
