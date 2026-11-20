# October severe-incident replay

Stage: **COMPLETE_VALIDATION**.

This report uses 257 predeclared checkpoints from 12 incident families. Checkpoints within an incident are correlated.

The Stay reference is the fastest unmodified MTA candidate at the same cutoff, across all 11 variants and 7 families. Each correction mode selects its own trains for that fixed route. Switch gain compares that mode's Stay and Switch trains; strategy gain against the original MTA train is a separate measure.

The selected MTA Stay reference had definite applicable severe context at 0 checkpoints (0 with fully verified comparison evidence), fresh normal context at 94, other known non-severe context at 49, unknown or ambiguous context at 114, and was unavailable at 0. The same-cutoff fastest MTA route may already avoid the incident; total selected incident checkpoints are therefore not all severe-affected Stay opportunities.

| Mode | Evidence scope | Switches | Scorable | Unknown | Gains >3 min | Ties | Losses >3 min | Incident-weighted gain rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| mta | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| mta | conditional_timing_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| time_profile | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| time_profile | conditional_timing_decision | 42 | 10 | 32 | 5 | 4 | 1 | 36.7% (5 incidents) |
| incident_profile | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| incident_profile | conditional_timing_decision | 45 | 10 | 35 | 5 | 4 | 1 | 55.6% (6 incidents) |

Strict advice requires fresh train and alert evidence with applicable severe context. Conditional timing results are diagnostics when strict evidence is unavailable, never formal advice success.

| Route family | Candidate observations | Timing available | Timing unavailable | Outcome inferred | Outcome missing | Missed selected train |
|---|---:|---:|---:|---:|---:|---:|
| 7_TO_23 | 514 | 448 | 66 | 130 | 317 | 67 |
| 7_TO_45 | 514 | 339 | 175 | 162 | 282 | 70 |
| E_TO_AC | 514 | 397 | 117 | 282 | 185 | 47 |
| F_DIRECT | 257 | 161 | 96 | 126 | 131 | 0 |
| G_DIRECT | 257 | 169 | 88 | 146 | 111 | 0 |
| NW_TO_R | 514 | 330 | 184 | 211 | 268 | 35 |
| R_DIRECT | 257 | 182 | 75 | 156 | 101 | 0 |

Unknown outcomes remain in coverage counts. A missed selected train or transfer is unknown; the evaluator never substitutes a later train using hindsight. Outcomes are screened final MTA prediction proxies, not independently observed physical arrivals.

Walking durations are authored research assumptions. Sensitivity uses the first checkpoint of the first three chronological incident families per split, regardless of outcomes, changing one candidate's one walking component by +/-120 seconds and recomputing all train choices and the MTA reference.

Sensitivity checkpoints evaluated: 3; variations: 180.

Per-period, weekday/Saturday/Sunday, split, incident, missed-opportunity, and candidate-outcome counts are in the JSON summary. Full selected-train evidence and every sensitivity variation are in deterministic compressed JSONL.

Full local case artifact: `algo/local/october/october-validation-cases.jsonl.gz` (SHA256 `fee725c27e3b0049bfafff131b25a1ec26f63f12039ec61d359292f322febd5f`).

No general severe-service success claim is warranted where incident or outcome coverage is insufficient.
