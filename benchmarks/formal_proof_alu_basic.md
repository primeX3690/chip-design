# Formal verification: `alu_basic`

**NOT EQUIVALENT (counterexample found)**

- seed: `designs/seed/alu_basic.v`
- evolved: `designs/best/alu_basic_best.v`
- design type: combinational
- deciding method: `yosys_sat_miter`

| method | ran | equivalent | bounded | seconds | note |
|---|---|---|---|---|---|
| yosys_sat_miter | True | False | False | 0.117 | SAT solver found a real counterexample -- designs differ (see log for the failing inputs/outputs). |

## What this does and does not show

- Equivalence is relative to the seed design; the seed's own correctness is not proven by this check.
- The proof is about Yosys' elaboration of both designs and relies on the SAT/SMT solver being correct.
- Only designs with identical port lists are comparable (mutation never changes the interface).
