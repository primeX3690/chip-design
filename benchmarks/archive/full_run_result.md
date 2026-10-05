# EvoHDL Baseline vs Evolved -- picorv32_alu

Baseline (human-written reference): `designs/seed/picorv32_alu.v`
Evolved (GA best individual): `designs/best/picorv32_alu_best.v`

| Metric | Baseline | Evolved | Improvement |
|---|---|---|---|
| Cell count (generic synth) | 1318 | 1318 | +0.0% |
| Logic depth (levels, Yosys `ltp`) | 23 | 23 | +0.0% |

Cell count and logic depth are technology-independent Yosys `synth` proxies
(fast, used as the GA's per-generation fitness signal). For real,
silicon-referenced numbers (um^2 die area on SkyWater 130nm, picosecond
timing, routed FPGA congestion), see `benchmarks/hardware_verification_report.md`,
produced by `hardware_verification_pipeline.py` via OpenLane + OpenSTA +
nextpnr.
