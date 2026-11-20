# November weekday interpretation and operational limits

This note interprets the frozen [weekday evaluation](november-weekday-test.md) after outcome scoring. It does not change the selected cohort, model, forecasts, thresholds or recorded results. The final reporting dates are November 2–6, 9–13 and 16–18, 2026. October 1–31 supplies training; November 19 supplies boundary evidence only. November 2–15 overlaps earlier project exploration.

The [independent aggregate audit](november-weekday-summary-independent-audit.json) passed 130,397 checks with no mismatches. The [positive-endpoint and original-source audit](november-weekday-positive-endpoint-audit.json) passed 8,300 checks: 123 unique train/stop records serving 124 target endpoints, plus the two earlier-local-7 witness endpoints, match the original CSV journals and raw GTFS-RT confirmation receipts. These checks validate the recorded evidence and arithmetic; they do not turn forecast proxies into independent passenger measurements.

## What the comparison supports

At the 197 earliest qualified weekday corridor/publisher-family checkpoints, the incident-aware model made 34 Switch recommendations: 11 had a meaningful proxy-time gain, one was a practical tie, one lost meaningful time and 21 had unknown complete outcomes. Comparing each policy's actual selected journey, the incident model and raw-MTA policy had 81 comparable primary decisions: seven gains, 73 ties and one loss. Another 36 pairs had concrete actions but incomplete outcomes.

Across all 2,306 repeated checkpoints, the model made 287 Switch recommendations: 99 gains, 16 ties, two losses and 170 unknowns. These repeated checkpoints are useful for studying how an incident evolves, but they are not 2,306 independent incidents or actual passenger journeys. Publisher IDs can also describe a common underlying fault.

Decision coverage is limited as well: the model returns 749 Stay, 287 Switch and 1,270 Undetermined actions. Thus 1,036 of 2,306 checkpoints receive a concrete decision; a usable ETA for one route does not necessarily provide enough evidence to compare every supplied alternative.

The model changed raw-MTA Stay into Switch at 58 checkpoints. Of the 22 with complete selected-policy outcomes, 13 gained more than three minutes and nine were practical ties; 36 remained unknown. The 13 positive cases have distinct publisher IDs and cover four corridors: Port Authority–Tandon (five), Times Square–Borough Hall (four), Grand Central–Borough Hall (three), and Court Square–Times Square (one). Their frozen selected-train gains range from 3.37 to 14.28 minutes, with a median of 6.45 minutes. This is evidence that useful advice is possible, not a general accuracy or passenger success rate.

The newly unused November 16–18 subset is weaker evidence of incremental model value: among 18 comparable primary incident-model versus raw-MTA decisions, there was one gain, 16 ties and one loss. Its two primary raw-Stay/model-Switch cases both have unknown complete outcomes.

## Incident context has not established an advantage over time-only history

Among 79 comparable primary incident-profile versus time-profile decisions, 78 were ties and one was a loss; none gained more than three minutes. Across all repeated checkpoints the corresponding counts were 12 gains, 642 ties and ten losses. Thus these results do not establish that adding the incident-specific adjustment improves on time-conditioned history. They do justify retaining the simpler time-only baseline in future comparisons.

The severe subset contains 183 checkpoints from 12 corridor/publisher families, representing 11 publisher IDs. It produced 34 model Switch recommendations: ten gains, one tie, no observed complete-outcome loss and 23 unknowns. Only one of the overall earliest primary checkpoints was already severe: other incidents escalated later. Severe evidence therefore mainly comes from repeated observations within incident windows. Explicit severe wording and official warnings of complete fixed-path interruption remain distinct; a warning can conflict with a continuing through-service forecast. Neither a selected-train proxy nor the notice alone independently establishes physical train movement.

## A passenger can take an earlier Stay train

The frozen comparison holds each policy to its forecast-selected train sequence. The independent [same-cutoff Stay audit](november-weekday-same-cutoff-stay-audit.json) also checked other Stay trains already visible at that same decision cutoff.

All 13 narrow positive cases remain meaningful gains against screened Stay trains that were catchable according to their raw forecasts. When the audit additionally allows an already-visible train whose raw forecast appeared uncatchable but whose final proxy departure was catchable, 12 cases remain gains and one becomes a tie. No case becomes a loss in that audit.

The changed case is Court Square–Times Square on November 11 at 09:50:25: the selected local 7 versus F comparison saved 857 seconds, but an earlier local 7 already visible in the same feed reduces that advantage to 82 seconds. This limitation matters for a decision companion: a passenger waiting on Stay may board that earlier train. The main frozen counts remain unchanged; the separate sensitivity is 12 gains and one tie among those 13 selected positive examples, not a new overall study denominator.

A [separate audit of the ten model-versus-own-Stay gains above 15 minutes](november-weekday-large-gain-same-cutoff-stay-audit.json) finds nine gains and one tie against the best screened actually catchable same-cutoff Stay train. These ten examples are not additional raw-Stay/model-Switch evidence: raw MTA already recommends Switch in nine and is undetermined in one. Comparing their actual selected policies gives three gains, four ties, one loss and two unknowns. The largest reported gain against the model's own Stay train, 3,077 seconds, is actually a 213-second loss against the raw policy's selected journey. A large improvement over a delayed reference route must not be presented as the model's incremental benefit over raw MTA.

| Local decision time | Corridor | Stay → Switch | Frozen proxy saving | Interpretation |
|---|---|---|---:|---|
| Nov 5, 17:06 | Grand Central → Borough Hall | 5 → 4 | 6.45 min | Downtown 4/5 delay notice; direct alternative service from the same origin station. |
| Nov 5, 21:35 | Port Authority → Tandon | A → C | 3.37 min | Explicit severe downtown A delays after track debris removal. |
| Nov 5, 22:39 | Times Square → Borough Hall | 2 → 3 | 6.45 min | NYPD investigation affecting 2 service; the sole positive raw-Stay/model-Switch primary checkpoint. |
| Nov 11, 09:50 | Court Square → Times Square | 7 → F | 14.28 min | Signal problem; falls to a 1.37-minute tie against the earlier actual-catchable same-cutoff 7 train. |
| Nov 18, 07:27 | Port Authority → Tandon | A → C | 8.95 min | Downtown A/C signal problem near Chambers Street; both services can be affected yet one selected train can arrive sooner. |

These examples were chosen after scoring to illustrate behavior. They are not an independently selected validation sample. All travel times remain screened MTA final-prediction proxies plus declared walks.

## Catchability and missing route details are practical blockers

The incident model has 137 known missed selected journeys, versus 75 for raw MTA. Model misses comprise 86 Stay and 51 Switch actions, with 128 first-leg and nine transfer misses. These are explicit operational failures with unknown complete travel time; they are not successful advice or practical ties. A positive historical departure correction can make a train appear catchable even when its screened final departure precedes platform readiness. The [operational diagnostic](november-weekday-operational-diagnostics.json) records the matched evidence and affected case IDs. These observations motivate a separate boarding-feasibility guard before relying on corrected departure times in production; no such rule was added after this study was frozen.

Among the 992 checkpoints where both policies produce a concrete action, 69 have a completed raw-policy proxy journey but a missed model journey; 23 have the reverse pattern, and both policies miss in 51. In 78 model misses, the selected train's raw departure forecast was before forecast platform readiness but the corrected departure was after it; 76 are first-leg cases with the same access time. The 170 unknown model Switch outcomes consist of 51 missed selected Switch trains, 58 unusable selected-Switch endpoint records, and 61 completed selected-Switch proxy journeys whose Stay comparison is unavailable or missed. Reporting only the 99 gains among the 117 complete model-Switch comparisons would hide these operational and evidence limits.

The pilot corridor has no model Stay actions for a structural reason. One supplied E→A provider candidate lacks a transfer-walking duration, so the algorithm cannot certify that every supplied alternative was compared. Of 691 pilot checkpoints, 74 produce Switch, 348 are undetermined because alternatives are unassessed, 179 have unverified current-service evidence and 90 have no usable current route. Zero Stay therefore does not mean that switching was always preferable. Completing provider itinerary details is necessary to measure useful Stay coverage.

## Walking sensitivity

Four raw-Stay/model-Switch journeys with a positive numerical proxy gain have only 3.27–9.30 seconds between declared platform readiness and inferred initial departure; two of these cases are already practical ties. The original-source audit confirms the recorded timestamps, but these are assumption-sensitive catches, not guaranteed passenger boardings. No retrospective boarding margin was introduced into the frozen results.

The frozen sensitivity analysis evaluates 1,509 variants across the 197 primary checkpoints. At least one allowed walking-component perturbation changes the action in 51 primary cases. These are sensitivity scenarios, not extra success samples. For Port Authority, the additional coupled A/C access assumptions of zero or 240 seconds produce 92 variants across 46 primaries; two change Stay to Switch and 90 preserve the action.

The Times Square November 5 primary positive example is also sensitive: increasing Switch access by two minutes, or shrinking its relative egress advantage by two minutes, changes the advice to Stay. The baseline still supplies a useful fixed-assumption example, but its recommendation should not be presented as robust to walking uncertainty.

The immediate product priorities supported by this study are complete provider itinerary inputs, boarding feasibility that does not rely solely on average ETA delay, clear unknown states, and continued comparison with the time-only baseline. The frozen results demonstrate some useful decisions; they do not yet establish reliable severe-incident superiority or universal Switch accuracy.
