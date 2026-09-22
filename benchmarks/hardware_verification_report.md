# EvoHDL Hardware Verification Report -- picorv32_alu

Generated: 2026-09-17T04:54:47.548850+00:00
Baseline (human-written reference): `designs/seed/picorv32_alu.v`
Evolved (GA best individual): `designs/best/picorv32_alu_best.v`

## 1. Generic synthesis (Yosys `synth`, technology-independent)

| Metric | Baseline | Evolved | Improvement |
|---|---|---|---|
| Cell count | 1409 | 1409 | +0.0% |
| Logic depth (levels) | 23 | 23 | +0.0% |

## 2. Real ASIC flow -- OpenLane + SkyWater 130nm (sky130_fd_sc_hd)

_Not available: Docker not found -- install Docker + `pip install volare` and run `volare enable <pdk-version>` first (see README.md)._

## 3. Real static timing analysis -- OpenSTA (sky130 liberty)

_Not available: OpenSTA ('sta') not on PATH_

## 4. Real FPGA place-and-route -- nextpnr-ice40 (no board required)

- **Routed critical path:** 15.45 ns
- **Implied max frequency:** 64.7 MHz
- **Logic cells used:** 648 / 7680
- **I/O used:** 100 / 256

---
_Stages 1 and 4 run on any machine with Yosys + Verilator + nextpnr-ice40 installed (all apt-installable). Stages 2-3 need Docker + the sky130 PDK (via `volare`) + a built OpenSTA binary -- see README.md 'Real Hardware Verification Flow' for setup. Any stage marked 'Not available' above was skipped, not faked -- rerun after installing its tool to fill it in._