# November weekday boarding repair and route-execution results

This separately versioned repair uses the same 2,306 checkpoints, 197 earliest weekday corridor/publisher-family representatives, five corridors and October 1–31 model as the preserved November study. Dates are November 2–6, 9–13 and 16–18, 2026. These dates have already been examined: this is a post-hoc repair regression, not a new untouched test. No retraining or outcome-based case selection was performed.

The main boarding margin is 120 seconds. Positive historical departure correction cannot make an otherwise uncatchable train eligible. Transfers use conservative platform readiness. The margin is an eligibility rule, not extra travel time. All three prediction policies use the same rule.

The execution evaluator follows the frozen route and boards the first evidenced compatible train after platform readiness. It uses archived future feed evidence only to reconstruct movement, never to select the earliest eventual destination arrival. It can continue on a later train after a forecast-selected train is missed. Ambiguous earlier trains, missing evidence and incomplete coverage remain unknown; the elapsed horizon is 120 minutes. Times remain screened final-MTA-prediction proxies plus declared walks, not independently measured passenger journeys.

## Main outcome counts

| Scope | Checkpoints | Families | Switch | Gain >3 min | Tie | Loss >3 min | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|
| All weekdays | 2306 | 197 | 339 | 23 | 13 | 4 | 299 |
| Earliest representatives | 197 | 197 | 34 | 3 | 2 | 1 | 28 |
| November 16–18 | 442 | 42 | 49 | 3 | 3 | 0 | 43 |
| November 16–18 representatives | 42 | 42 | 5 | 0 | 0 | 0 | 5 |
| Qualified severe | 183 | 12 | 51 | 0 | 0 | 0 | 51 |

All-checkpoint rows retain repeated times within incidents. Publisher IDs are not necessarily independent physical faults. Predicted Switch savings must still reach five minutes; outcome differences within ±3 minutes are ties.

## Five-corridor detail

| Corridor | Checkpoints | Families | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|
| pilot_hayden_tandon | 691 | 63 | 121 | 11 | 4 | 2 | 104 |
| grandcentral_boroughhall | 479 | 37 | 81 | 5 | 7 | 1 | 68 |
| courtsquare_timessquare | 156 | 13 | 19 | 0 | 0 | 0 | 19 |
| timesquare_boroughhall | 362 | 38 | 64 | 7 | 2 | 0 | 55 |
| portauthority_tandon | 618 | 46 | 54 | 0 | 0 | 1 | 53 |

## Policy comparisons under identical route execution

| Scope / comparison | Concrete pairs | Comparable | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekdays / time_vs_mta | 1020 | 378 | 2 | 370 | 6 | 642 |
| All weekdays / incident_vs_mta | 1019 | 374 | 2 | 366 | 6 | 645 |
| All weekdays / incident_vs_time | 1038 | 390 | 3 | 384 | 3 | 648 |
| Earliest representatives / time_vs_mta | 116 | 37 | 0 | 36 | 1 | 79 |
| Earliest representatives / incident_vs_mta | 116 | 38 | 0 | 37 | 1 | 78 |
| Earliest representatives / incident_vs_time | 118 | 40 | 0 | 40 | 0 | 78 |

These compare the routes actually chosen by each policy. A faster Switch relative to its own Stay does not automatically imply an improvement over the raw-MTA policy.

## Raw-MTA Stay / model Switch

| Scope | Cases | Comparable | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekdays | 61 | 7 | 2 | 4 | 1 | 54 |
| Earliest representatives | 2 | 0 | 0 | 0 | 0 | 2 |
| November 16–18 | 5 | 0 | 0 | 0 | 0 | 5 |
| November 16–18 representatives | 1 | 0 | 0 | 0 | 0 | 1 |
| Qualified severe | 9 | 0 | 0 | 0 | 0 | 9 |

## Separate evaluator changes from prediction changes

| Evaluation / model version | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|
| Original exact-train evaluator / old model | 287 | 99 | 16 | 2 | 170 |
| New route executor / old model | 287 | 15 | 7 | 3 | 262 |
| New route executor / repaired model | 339 | 23 | 13 | 4 | 299 |

The second row holds the old recommendations fixed and changes only execution scoring. The third adds the boarding repair. Exact-train missed-boardings remain diagnostics even when the route later completes.

| Matched old/new recommendation | Concrete pairs | Comparable | New faster | Tie | New slower | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekdays | 1005 | 329 | 5 | 316 | 8 | 676 |
| Earliest representatives | 116 | 31 | 0 | 30 | 1 | 85 |

## Boarding diagnostics and remaining unknowns

| Version / policy | Concrete actions | Exact selected-train misses | Switch actions | Missed Switch trains | Missed selected train but route completes |
|---|---:|---:|---:|---:|---:|
| Old / mta | 1020 | 75 | 253 | 20 | 32 |
| Old / time_profile | 1013 | 111 | 271 | 44 | 47 |
| Old / incident_profile | 1036 | 137 | 287 | 51 | 57 |
| Repaired / mta | 1021 | 3 | 246 | 2 | 0 |
| Repaired / time_profile | 1041 | 2 | 303 | 0 | 1 |
| Repaired / incident_profile | 1082 | 1 | 339 | 0 | 0 |

The separate departure-first check below does not require a usable destination-arrival record to identify a missed first boarding. Later boardings require the preceding leg's arrival to establish platform readiness.

| Version / policy | Concrete actions | Evaluable first boardings | Missed first boardings | Unknown first boardings | Evaluable full boarding sequences | Missed sequence | Unknown sequence |
|---|---:|---:|---:|---:|---:|---:|---:|
| Old / mta | 1020 | 889 | 74 | 131 | 884 | 79 | 136 |
| Old / time_profile | 1013 | 879 | 112 | 134 | 875 | 117 | 138 |
| Old / incident_profile | 1036 | 899 | 141 | 137 | 893 | 150 | 143 |
| Repaired / mta | 1021 | 888 | 1 | 133 | 886 | 5 | 135 |
| Repaired / time_profile | 1041 | 909 | 2 | 132 | 908 | 3 | 133 |
| Repaired / incident_profile | 1082 | 938 | 1 | 144 | 936 | 1 | 146 |

The repaired model has 299 unknown Switch comparisons: 190 with an incomplete chosen route and 109 with a completed chosen route but incomplete Stay. These groups are mutually exclusive.

| Exclusive unknown reason | Count |
|---|---:|
| chosen:UNAVAILABLE:FIRST_BOARDABLE_TRAIN_ARRIVAL_UNAVAILABLE | 1 |
| chosen:UNAVAILABLE:INSUFFICIENT_FEED_COVERAGE | 4 |
| chosen:UNAVAILABLE:UNRESOLVED_EARLIER_BOARDING | 185 |
| stay:UNAVAILABLE:INSUFFICIENT_FEED_COVERAGE | 4 |
| stay:UNAVAILABLE:UNRESOLVED_EARLIER_BOARDING | 105 |

A missed selected train remains an operational failure under the declared walking assumptions even if the route eventually completes. Unknown or censored travel time never becomes zero or a successful recommendation.

## Boarding-margin sensitivity on the 197 representatives

| Margin seconds | Switch | Gain | Tie | Loss | Unknown | Known selected-train misses |
|---|---:|---:|---:|---:|---:|---:|
| 60 | 33 | 2 | 1 | 1 | 29 | 1 |
| 120 | 34 | 3 | 2 | 1 | 28 | 0 |
| 180 | 30 | 2 | 3 | 1 | 24 | 0 |

The sensitivity cases are the same original representatives, not additional performance samples. The main 120-second setting was declared before these repair forecasts; these previously examined dates do not justify selecting an apparently best margin and calling it independently validated.

## Reproduction

```sh
.venv/bin/python algo/scripts/evaluate_november_repair.py --freeze-only
.venv/bin/python algo/scripts/evaluate_november_repair.py --verify-only
.venv/bin/python algo/scripts/evaluate_november_repair.py
```

[Full results and provenance](november-repair-test.json) · [Frozen repair policy and inputs](november-repair-selection-frozen.json)
