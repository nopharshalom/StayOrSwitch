# October severe-incident replay

Stage: **COMPLETE_TEST**.

This report uses 128 predeclared checkpoints from 6 incident families. Checkpoints within an incident are correlated.

The Stay reference is the fastest unmodified MTA candidate at the same cutoff, across all 11 variants and 7 families. Each correction mode selects its own trains for that fixed route. Switch gain compares that mode's Stay and Switch trains; strategy gain against the original MTA train is a separate measure.

The selected MTA Stay reference had definite applicable severe context at 0 checkpoints (0 with fully verified comparison evidence), fresh normal context at 49, other known non-severe context at 30, unknown or ambiguous context at 49, and was unavailable at 0. The same-cutoff fastest MTA route may already avoid the incident; total selected incident checkpoints are therefore not all severe-affected Stay opportunities.

| Mode | Evidence scope | Switches | Scorable | Unknown | Gains >3 min | Ties | Losses >3 min | Incident-weighted gain rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| mta | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| mta | conditional_timing_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| time_profile | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| time_profile | conditional_timing_decision | 10 | 4 | 6 | 3 | 0 | 1 | 66.7% (3 incidents) |
| incident_profile | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 | N/A |
| incident_profile | conditional_timing_decision | 14 | 4 | 10 | 2 | 1 | 1 | 50.0% (3 incidents) |

Strict advice requires fresh train and alert evidence with applicable severe context. Conditional timing results are diagnostics when strict evidence is unavailable, never formal advice success.

| Route family | Candidate observations | Timing available | Timing unavailable | Outcome inferred | Outcome missing | Missed selected train |
|---|---:|---:|---:|---:|---:|---:|
| 7_TO_23 | 256 | 235 | 21 | 107 | 119 | 30 |
| 7_TO_45 | 256 | 197 | 59 | 92 | 149 | 15 |
| E_TO_AC | 256 | 204 | 52 | 156 | 78 | 22 |
| F_DIRECT | 128 | 97 | 31 | 74 | 54 | 0 |
| G_DIRECT | 128 | 115 | 13 | 107 | 20 | 1 |
| NW_TO_R | 256 | 183 | 73 | 117 | 113 | 26 |
| R_DIRECT | 128 | 80 | 48 | 69 | 59 | 0 |

Unknown outcomes remain in coverage counts. A missed selected train or transfer is unknown; the evaluator never substitutes a later train using hindsight. Outcomes are screened final MTA prediction proxies, not independently observed physical arrivals.

Walking durations are authored research assumptions. Sensitivity uses the first checkpoint of the first three chronological incident families per split, regardless of outcomes, changing one candidate's one walking component by +/-120 seconds and recomputing all train choices and the MTA reference.

Sensitivity checkpoints evaluated: 3; variations: 180.

Per-period, weekday/Saturday/Sunday, split, incident, missed-opportunity, and candidate-outcome counts are in the JSON summary. Full selected-train evidence and every sensitivity variation are in deterministic compressed JSONL.

Full local case artifact: `algo/local/october/october-test-cases.jsonl.gz` (SHA256 `5e36a1c30bf391e2ca639be129a6eaadd612cf106d515577207a9eec1557a577`).

No general severe-service success claim is warranted where incident or outcome coverage is insufficient.
