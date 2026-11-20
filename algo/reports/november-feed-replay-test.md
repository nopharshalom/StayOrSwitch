# November weekday visible-feed execution results

This version changes only historical route execution. It reuses the exact frozen two-minute boarding-safe forecasts, full October model, 2,306 weekday checkpoints, 197 earliest corridor/notice-family representatives and five corridors. Dates are November 2–6, 9–13 and 16–18, 2026. They have already been examined; this is a post-hoc replay comparison, not a new untouched test. No advice was regenerated or selected using outcomes.

After the initial visible-feed run was scored, source review found a collapsed prediction sequence that implied a ten-second ride from Port Authority to Jay Street. The initial run is preserved by hash. This corrected report adds a symmetric selected-leg outcome screen: straight-line station distance divided by the inferred ride duration must not exceed 300 km/h. This is a deliberately permissive sanity ceiling, not a claim about subway operating speeds or an estimator of normal travel time. The rule was added after seeing initial outcomes and is explicitly a post-hoc quality repair. It rejects unusable evidence for the already selected train; it never picks a different train to obtain a complete or better result.

At the platform, the simulated passenger chooses the earliest compatible service using the raw departure ETA in the currently visible feed. Later visible updates can change that choice. Final endpoint quality and eventual destination arrival do not rank candidates. Unknown records for unselected trains no longer block execution. Missing or unusable evidence for the selected train, unresolved selected disappearance and feed gaps remain explicit. Only the selected train's screened records infer movement; these are MTA prediction proxies plus authored walks, not independent passenger observations.

A compatible service still present in the current feed with an expired departure ETA is treated as due now. It is selected normally rather than discarded through historical final labels; missing evidence for that selected due-now train yields an explicit unknown result.

If an initially selected train lacks final departure evidence, a later feed update before its currently predicted boarding time may change the choice. A completed journey after that interval is conditional on the feed-following waiting assumption; its inferred final train does not independently prove what happened during the earlier unverified wait. Such comparisons are counted and separated below.

The original two-minute boarding gate remains unchanged in all recommendation policies. It is not added again while the passenger is already at the platform. Predicted Switch savings require five minutes; outcome differences within ±3 minutes are ties. The execution horizon remains two hours.

## Main outcome counts

| Scope | Checkpoints | Families | Switch | Gain >3 min | Tie | Loss >3 min | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|
| All weekdays | 2306 | 197 | 339 | 78 | 70 | 25 | 166 |
| Earliest representatives | 197 | 197 | 34 | 10 | 8 | 3 | 13 |
| November 16–18 | 442 | 42 | 49 | 5 | 12 | 1 | 31 |
| November 16–18 representatives | 42 | 42 | 5 | 0 | 1 | 0 | 4 |
| Qualified severe | 183 | 12 | 51 | 5 | 8 | 2 | 36 |

Repeated checkpoints and publisher IDs are not independent passenger journeys or physical faults.

## Evidence for completed Switch comparisons

| Scope | Without unverified selected wait | Conditional on an unverified selected wait |
|---|---:|---:|
| All weekdays | 170 | 3 |
| Earliest representatives | 21 | 0 |
| Qualified severe | 15 | 0 |

Both groups remain historical feed-policy simulations. The second group additionally depends on waiting through an interval whose selected departure could not be verified; it must not be described as independently confirmed actual passenger time saving.

## Five-corridor detail

| Corridor | Checkpoints | Families | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|
| pilot_hayden_tandon | 691 | 63 | 121 | 33 | 32 | 7 | 49 |
| grandcentral_boroughhall | 479 | 37 | 81 | 16 | 19 | 6 | 40 |
| courtsquare_timessquare | 156 | 13 | 19 | 3 | 3 | 1 | 12 |
| timesquare_boroughhall | 362 | 38 | 64 | 23 | 9 | 3 | 29 |
| portauthority_tandon | 618 | 46 | 54 | 3 | 7 | 8 | 36 |

## Raw-MTA Stay / model Switch

| Scope | Cases | Comparable | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekdays | 61 | 31 | 13 | 14 | 4 | 30 |
| Earliest representatives | 2 | 1 | 0 | 1 | 0 | 1 |
| November 16–18 | 5 | 0 | 0 | 0 | 0 | 5 |
| November 16–18 representatives | 1 | 0 | 0 | 0 | 0 | 1 |
| Qualified severe | 9 | 2 | 0 | 2 | 0 | 7 |

## Policy comparisons with identical feed-following execution

| Scope / comparison | Concrete pairs | Comparable | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekdays / time_vs_mta | 1020 | 737 | 18 | 706 | 13 | 283 |
| All weekdays / incident_vs_mta | 1019 | 727 | 18 | 694 | 15 | 292 |
| All weekdays / incident_vs_time | 1038 | 734 | 11 | 710 | 13 | 304 |
| Earliest representatives / time_vs_mta | 116 | 80 | 1 | 77 | 2 | 36 |
| Earliest representatives / incident_vs_mta | 116 | 79 | 0 | 78 | 1 | 37 |
| Earliest representatives / incident_vs_time | 118 | 80 | 1 | 78 | 1 | 38 |

Own-Stay gains do not establish incremental model gains over the raw-MTA policy. All policies share the same route execution and walking assumptions.

## Changed evaluator, unchanged advice

| Scope / evaluator | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|
| All weekdays / strict first-service ordering | 339 | 23 | 13 | 4 | 299 |
| All weekdays / visible-feed choices | 339 | 78 | 70 | 25 | 166 |
| Earliest representatives / strict first-service ordering | 34 | 3 | 2 | 1 | 28 |
| Earliest representatives / visible-feed choices | 34 | 10 | 8 | 3 | 13 |
| Qualified severe / strict first-service ordering | 51 | 0 | 0 | 0 | 51 |
| Qualified severe / visible-feed choices | 51 | 5 | 8 | 2 | 36 |

Only the evaluator changes between these rows. Route recommendations, selected forecast trains, model and margins are byte-for-byte reused. Changes in inferred savings or coverage are not new algorithm advice.

## Outcome-quality correction after the initial feed replay

| Scope / evidence screen | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|
| All weekdays / superseded initial screen | 339 | 80 | 70 | 25 | 164 |
| All weekdays / corrected selected-leg screen | 339 | 78 | 70 | 25 | 166 |
| Earliest representatives / superseded initial screen | 34 | 10 | 8 | 3 | 13 |
| Earliest representatives / corrected selected-leg screen | 34 | 10 | 8 | 3 | 13 |
| Qualified severe / superseded initial screen | 51 | 7 | 8 | 2 | 34 |
| Qualified severe / corrected selected-leg screen | 51 | 5 | 8 | 2 | 36 |

Across all supplied paths, 11 selected route queries involving 5 unique train/segment pairs are rejected by the physical sanity screen. Raw endpoint values and the rejection evidence remain in the result artifacts. Rejected route evidence becomes unknown and is never replaced with a forecast, a clamped duration, or another train chosen using final labels.

[Post-initial-score quality addendum](../docs/november-feed-outcome-quality-addendum.md)

## Matched old and boarding-safe advice under the new evaluator

| Scope | Concrete pairs | Comparable | Boarding-safe faster | Tie | Boarding-safe slower | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekdays | 1005 | 672 | 16 | 620 | 36 | 333 |
| Earliest representatives | 116 | 76 | 1 | 70 | 5 | 40 |

## Preserved boarding diagnostics

| Version / policy | Concrete actions | Evaluable boarding sequences | Missed | Unknown | Switch sequences evaluable | Missed Switch | Unknown Switch |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original / mta | 1020 | 884 | 79 | 136 | 210 | 20 | 43 |
| Original / time_profile | 1013 | 875 | 117 | 138 | 227 | 45 | 44 |
| Original / incident_profile | 1036 | 893 | 150 | 143 | 240 | 57 | 47 |
| Boarding-safe / mta | 1021 | 886 | 5 | 135 | 208 | 4 | 38 |
| Boarding-safe / time_profile | 1041 | 908 | 3 | 133 | 266 | 1 | 37 |
| Boarding-safe / incident_profile | 1082 | 936 | 1 | 146 | 288 | 0 | 51 |

These independently preserved diagnostics concern the initially forecast-selected trains. Feed-following execution may select another train; eventual route completion does not erase an initial boarding-feasibility error.

## Remaining unknown Switch comparisons

| Exclusive reason | Count |
|---|---:|
| chosen:UNAVAILABLE:SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME | 2 |
| chosen:UNAVAILABLE:SELECTED_SERVICE_DISAPPEARED | 32 |
| chosen:UNAVAILABLE:SELECTED_TRAIN_ARRIVAL_UNAVAILABLE | 9 |
| chosen:UNAVAILABLE:SELECTED_TRAIN_DEPARTURE_UNAVAILABLE | 49 |
| chosen:UNAVAILABLE:UNUSABLE_FEED_CAPTURE | 1 |
| stay:UNAVAILABLE:SELECTED_SERVICE_DISAPPEARED | 35 |
| stay:UNAVAILABLE:SELECTED_TRAIN_DEPARTURE_UNAVAILABLE | 35 |
| stay:UNAVAILABLE:UNUSABLE_FEED_CAPTURE | 3 |

There are 166 unknown comparisons: 93 incomplete chosen routes, and 73 completed chosen routes with incomplete Stay. Unknown or censored duration is never replaced with a forecast or counted as a win.

## Selected-route execution traces

| Policy | Concrete route queries | Inferred | Unavailable | Censored | Missed selected-service attempts | Reselections |
|---|---:|---:|---:|---:|---:|---:|
| mta | 1021 | 750 | 271 | 0 | 136 | 225 |
| time_profile | 1041 | 754 | 287 | 0 | 142 | 228 |
| incident_profile | 1082 | 785 | 297 | 0 | 138 | 217 |

For model Switch routes specifically, the executor records 30 missed selected-service attempts and 43 reselections. These concern choices from the feed after reaching the platform; they are separate from the unchanged initial forecast-selected boarding diagnostic above. One journey can contain several attempts, and repeated checkpoints can reuse a train.

Full chronological choice updates and selected evidence are retained in the hashed local shared execution artifact. The JSON report includes update counters; queries across policies are not independent journeys.

## Preserved boarding-margin sensitivity

| Margin seconds | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|
| 60 | 33 | 8 | 7 | 2 | 16 |
| 120 | 34 | 10 | 8 | 3 | 13 |
| 180 | 30 | 10 | 6 | 3 | 11 |

These are the same frozen 197-case margin scenarios, not new cases or newly fitted predictions.

## Reproduction

```sh
.venv/bin/python algo/scripts/evaluate_november_feed_replay.py --freeze-only
.venv/bin/python algo/scripts/evaluate_november_feed_replay.py --verify-only
.venv/bin/python algo/scripts/evaluate_november_feed_replay.py
```

[Full results and provenance](november-feed-replay-test.json) · [Frozen inputs and execution policy](november-feed-replay-selection-frozen.json)
