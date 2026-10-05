# Customer discovery guide (20 conversations, 30 minutes each)

Rules: do not pitch for the first 15 minutes; ask about their last project; take verbatim quotes; never promise features.

## Opening
"Tell me about the last digital design you took to synthesis or to a chip/FPGA. What tools did you use and why?"

## Questions
1. Which synthesis/verification tools do you use today? Open source, commercial, or both? Who pays for the licences?
2. What was the most painful step in the last project (area/timing closure, verification, tool setup, licences, support)?
3. How do you check that a synthesized or optimized netlist still matches the RTL? How long does that take? Has it ever failed?
4. Have you ever left area or timing on the table because you ran out of time/licences? How much, in your estimate?
5. If a tool shrank area by 3-5% *and* produced a machine-checkable equivalence proof, what would you need to see before using it on a real project?
6. What would make you refuse it (trust, flow integration, support, data privacy, tool lock-in)?
7. Who else decides (advisor, department, funding body)? What would a purchase or pilot look like in your organisation?
8. If this existed today, how would you expect to pay for it (per seat, per project, institute-wide licence, support contract)? What range feels normal?
9. What are 2 other teams who have this problem?

## Close
"Would you run it on one real design in the next 60 days? Can I send you a pilot protocol?" -> record yes / maybe / no.

## Tracking sheet (copy into a spreadsheet)
`date, name, org, role, segment (lab/startup/MPW/fabless), tools used, top pain, pays for EDA? (y/n), would pilot (y/m/n),
budget signal, referrals, verbatim quote, next step`

## What counts as signal
Strong: they name a concrete current project, volunteer a design, or introduce a colleague. Weak: "sounds interesting".
Kill criteria: after 20 conversations nobody has a pain that optimization or equivalence proofs address.
