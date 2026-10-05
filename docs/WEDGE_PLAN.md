# Wedge plan: "verified optimization on top of the open-source flow"

Status: a **hypothesis to test**, not a validated market. Everything below is written so it can be proven wrong quickly.

## 1. Positioning (one sentence)
A drop-in, formally verified optimization and equivalence layer for Yosys/OpenLane/OpenROAD flows, for teams that cannot
afford commercial EDA licences (university labs, C2S/ChipIN startups, small fabless teams, open-MPW designers) -- with an
"indigenous, auditable EDA" angle for programmes that want Indian-owned tooling.

What we do NOT claim: replacing Synopsys/Cadence, signoff quality, "AI-powered" anything, 100% proofs outside the stated
method, silicon results we have not measured.

## 2. Claims policy (what you may say, and when)
| Claim | Allowed only when |
|---|---|
| "X% smaller area than Yosys+ABC" | `benchmarks/reports/<run>/report.md` shows it on a REAL .lib, >= 10 designs incl. external suites, every pre-pass design verified (Yosys formal says PROVEN), losses listed |
| "Formally verified" | state the method (`PROVEN_UNBOUNDED` vs `PROVEN_BOUNDED N cycles`) exactly as the formal report does |
| "Works on real hardware" | an FPGA bitstream from the flow ran on a board, or a taped-out chip was measured; say which |
| "Indigenous EDA" | say what is ours (kernel, optimizer, CEC) and what is open source we call (Yosys, ABC, nextpnr, OpenLane) |
| "Revenue / customers" | signed pilots or LOIs exist |

## 3. Proof protocol (4-6 weeks) -- the go / no-go gate
1. v5 applied on a Linux/WSL2 box; `formal_pipeline --selftest` and `equivalence_checker --selftest` all PASS (fix scripts first).
2. `LIB=<real sky130 .lib> bash scripts/run_head_to_head.sh` -> read `report.md`. Add external designs (see
   `benchmarks/EXTERNAL.md`): PicoRV32 pieces, Ibex ALU/multiplier, OpenCores arithmetic, EPFL arithmetic suite.
3. Decision rule (set it BEFORE looking at results): geomean area reduction >= 3% on >= 10 verified designs for at least one
   flavor => the wedge has a technical basis; otherwise pivot the product to **verification/equivalence-checking as the
   product** (still valuable: formal pipeline, regression DB, proof reports) and treat optimization as a feature.
4. FPGA demo: `scripts/fpga_ice40_demo.sh` on a design where step 2 shows a win; photograph/record it on a board.
5. Optional silicon: take that design through OpenLane (sky130/gf180) to GDS; DRC/LVS clean; MPW shuttle via an open
   programme or, in India, the C2S/ChipIN route.

## 4. Customer discovery (run in parallel, not after)
Target 20 conversations: 8 university/IIT/NIT chip-design labs, 6 C2S/ChipIN/DLI startups, 3 open-MPW community designers, 3
small fabless teams. See `docs/CUSTOMER_DISCOVERY.md` for the interview guide and a tracking sheet. Success = 3+ people say
they would run the tool on a real project in the next 60 days and one agrees to a written pilot/LOI.
Hypotheses to test (do not assert): they are blocked by licence cost; they would trust a tool that proves equivalence;
they would pay (how much, how: per-seat, per-project, support contract, institute licence) -- let them tell you.

## 5. India programme checklist (verify every item with the official source before applying)
- DLI scheme (MeitY / ISM): product-design incentive (reported up to 50% of eligible cost, capped per application),
  EDA-tool grid access, MPW support. It targets chip/IP/SoC design products: **ask ISM whether an EDA-tool product company
  is eligible and under which category** before building the application around it.
- ChipIN Centre (C-DAC) / C2S: remote access to commercial EDA tools -> use it to benchmark our results against commercial flows.
- Semicon 2.0 (cabinet-approved July 2026): lists EDA/IP among focus areas; details were still being finalised -- watch ISM notices.
- Startup India / DPIIT recognition; institutional incubators (IITs, state startup missions). Do this early: it is cheap and
  unlocks other schemes.
Programmes change; terms in this file are a starting list, not advice.

## 6. Investor readiness checklist
- [ ] Reproducible head-to-head report on a real PDK library (not the bundled fictional one)
- [ ] >= 1 category with a verified win, or a clear pivot to verification
- [ ] FPGA demo (video) and, ideally, one measured MPW chip
- [ ] 3 pilots / LOIs; 20 interview notes
- [ ] A senior EDA / physical-design person on the team or as a named advisor (the biggest gap today)
- [ ] Licence audit (Yosys ISC, ABC, nextpnr ISC, Verilator LGPL, OpenLane Apache-2.0 -- confirm each) and a clear IP statement
- [ ] Company registered; IP assigned to the company; 12-18 month plan with milestones and a realistic ask

## 7. Honest risks
Optimization gains may be ~0 on well-written RTL (ABC is strong); large commercial vendors already ship AI-driven flows;
EDA sales cycles are long and customers trust track records; a solo non-EDA-veteran founder is a red flag for investors;
the pure-Python kernel will not scale to million-gate designs (would need a rewrite of hot paths in C++/Rust).
