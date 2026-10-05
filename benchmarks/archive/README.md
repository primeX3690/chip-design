# Archived results (historical, NOT current claims)

These were produced by earlier versions of the code, on different machines, and are kept only as a record.

- `full_run_result.*` -- picorv32_alu baseline vs evolved: **1318 vs 1318 cells, depth 23 vs 23 (0.0%)**.
- `hardware_verification_report.*` -- same comparison reported as **1409** cells. The 1318 vs 1409 gap is
  almost certainly a Yosys-version difference (the two runs were on different machines); the reports did not record
  the Yosys version. Newer reports do (`Yosys:` line), and now share one synthesis code path.
- `RUN_SUMMARY_alu_basic_30gen.md` -- 30-generation alu_basic run: best fitness 0.7490 at generation 0 and unchanged
  through generation 29, i.e. the search found nothing better after the initial population.

Deleted as misleading: identical gen12/26/32 snapshots, a benchmark report with `logic_depth = 0` (the old regex bug),
and a counter_4bit report produced before the sequential testbench existed (it compiled an ALU testbench against a
counter and failed).
