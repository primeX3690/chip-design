# Adding real benchmark suites

The default suite (`benchmarks/suite.json`) is small and partly synthetic. Investors/customers expect public designs.
Network access is needed to fetch them (not available where this repo was written). Check each project's licence before
redistributing; keep downloaded files OUT of the repo unless the licence allows it (use `benchmarks/external/`, git-ignored).

Suggested sources (verify current locations yourself): ISCAS-85/89 `.bench` files, EPFL combinational benchmarks (arithmetic
and random/control), OpenCores arithmetic blocks, PicoRV32 and Ibex arithmetic/ALU modules, open-source FPGA/ASIC demo cores.

## RTL designs
Add entries to a copy of `benchmarks/suite.json`:
```json
{"name": "ibex_alu", "files": ["benchmarks/external/ibex/ibex_alu.sv"], "top": "ibex_alu", "family": "external-rtl"}
```
Designs using generate blocks, functions, packages, `$signed` etc. are outside the native subset: they still get the Yosys
baselines and are reported as "native: unsupported / pre-pass n/a" (that is the honest picture of today's coverage). Extending
the parser/elaborator to cover them is the main engineering path to wider applicability.

## AIGER / BENCH circuits
`python -m evohdl.eda bench run-dir benchmarks/external` runs the native flow on `.bench`/`.aag` files (no Yosys comparison for
these; for a Yosys comparison provide Verilog).

Run: `python -m evohdl.eda compare --suite my_suite.json --lib <real.lib>`
