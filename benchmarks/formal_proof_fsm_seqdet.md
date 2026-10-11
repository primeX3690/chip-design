# Formal verification: `fsm_seqdet`

**PROVEN EQUIVALENT (unbounded: all inputs, all time)**

- seed: `seed`
- evolved: `fsm_seqdet_best.v`
- design type: sequential
- deciding method: `yosys_equiv_make+equiv_simple+equiv_induct`

| method | ran | equivalent | bounded | seconds | note |
|---|---|---|---|---|---|
| yosys_equiv_make | True | True | False | 0.031 | e |

## What this does and does not show

- Equivalence is relative to the seed design; the seed's own correctness is not proven by this check.
- The proof is about Yosys' elaboration of both designs and relies on the SAT/SMT solver being correct.
- Only designs with identical port lists are comparable (mutation never changes the interface).
