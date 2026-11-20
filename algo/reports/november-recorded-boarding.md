# November weekday Stay/Switch experiment using recorded departures

The October model's 595 recommendations, decision times, route options and walking durations are frozen. These observations come from November 2–6, 9–13 and 16–18, 2026. Repeated decisions can involve the same train or incident.

Both options board the earliest recorded train on the supplied line, direction and platform, including a departure exactly at readiness. A transfer starts at the selected train’s recorded arrival plus the supplied transfer walk. The allowed service IDs come from each frozen route template. For example, the Court Square Stay uses local 7 service.

The outcomes use final MTA journal timestamps screened for recency, passage confirmation and service changes, supplemented by bounded observations of stopped vehicles. For a passage without a reliable departure, the index screens possible order using its journal and observed-stop timestamps with a three-minute allowance on either end, bounded below by any verified arrival at that platform. This allowance can reduce coverage. An earlier unresolved passage, overlapping departures, an unconfirmed destination or an implausible journey leaves the comparison unknown. Missing arrival evidence never promotes the next train. Results describe reconstructed journeys among archived services; missing observations can conceal a train.

Any positive saving from following the recommendation counts as faster. Ties include zero saving and losses up to 10% of the reconstructed Stay duration. Larger losses count as slower. Percentages and minutes use classifiable cases. Time ranges reflect vehicle observation intervals.

| Corridor | Advice | Issued | Classified | Faster | Tie | Slower | Faster rate | Mean minutes saved | Median minutes saved |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Grand Central to Borough Hall | STAY | 289 | 109 | 66 | 27 | 16 | 60.6% | 1.57 | 2.42 |
| Grand Central to Borough Hall | SWITCH | 152 | 38 | 23 | 8 | 7 | 60.5% | 2.16 | 2.38 |
| Court Square to Times Square | STAY | 123 | 54 | 36 | 9 | 9 | 66.7% | 1.95 to 2.07 | 2.48 |
| Court Square to Times Square | SWITCH | 31 | 11 | 3 | 2 | 6 | 27.3% | -2.87 to -2.81 | -1.93 |

Classifiable comparisons: 212 of 595. Unresolved comparisons: 383.

## Switch outcomes on the same checkpoints

Each row includes only Switch recommendations that both replays could classify. Positive minutes mean switching saved time.

| Corridor | Paired checkpoints | Faster before | Faster now | Previous mean minutes saved | Current mean minutes saved |
|---|---:|---:|---:|---:|---:|
| Grand Central to Borough Hall | 37 | 21 | 23 | 2.21 | 2.41 |
| Court Square to Times Square | 9 | 7 | 3 | 14.55 to 14.64 | -2.84 to -2.76 |

## Unresolved comparisons

| Reason on either side | Cases |
|---|---:|
| UNRESOLVED_EARLIER_DEPARTURE | 364 |
| UNCERTAIN_BOARDING_AT_READINESS | 8 |
| UNCONFIRMED_DESTINATION_CALL_OR_ARRIVAL | 5 |
| UNCONFIRMED_DESTINATION_CALL_OR_ARRIVAL, UNRESOLVED_EARLIER_DEPARTURE | 5 |
| UNCERTAIN_BOARDING_AT_READINESS, UNRESOLVED_EARLIER_DEPARTURE | 1 |

[Case records](november-recorded-boarding.json) · [Replay inputs](../../data/artifacts/november-recorded-passages.json.gz) · [Previous forecast-boarding comparison](november-all-forecast-boarding-any-saving.md)
