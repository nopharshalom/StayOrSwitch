# November weekday Stay/Switch experiment

The October 1–31, 2026 historical ETA model supplied the frozen recommendations. The evaluation uses the November 2–6, 9–13 and 16–18 weekday cohort for two corridors selected after reviewing earlier results. Each observation is a recommendation time. Multiple decisions can involve the same trains or incident. The two corridors originally had 635 checkpoints. The table covers the 595 with Stay or Switch advice and excludes 10 Monitor and 30 Undetermined decisions. The sample includes service-problem checkpoints beyond the onset and across severity levels.

Both routes start at the same decision time and include walking, waiting and transfers. A passenger is assumed to board the earliest compatible train whose fresh MTA departure forecast is strictly later than platform readiness. The selected train needs a screened arrival from the journal or a bounded vehicle observation. These are reconstructed journeys.

Each comparison follows the original recommendation. Any positive saving counts as a gain. Zero saving or a loss up to and including 10% of the original Stay duration is a tie. A larger loss counts as slower. Percentages and time summaries use classifiable cases. Positive minutes indicate savings.

| Corridor | Advice | Issued | Classified | Faster | Tie | Slower | Faster rate | Mean minutes saved | Median minutes saved |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Grand Central to Borough Hall | STAY | 289 | 228 | 133 | 57 | 38 | 58.3% | 1.23 | 2.34 |
| Grand Central to Borough Hall | SWITCH | 152 | 113 | 70 | 20 | 23 | 61.9% | 2.63 | 2.17 |
| Court Square to Times Square | STAY | 123 | 92 | 61 | 17 | 14 | 66.3% | 1.76 to 1.84 | 2.28 to 2.43 |
| Court Square to Times Square | SWITCH | 31 | 18 | 14 | 0 | 4 | 77.8% | 12.06 to 12.10 | 13.95 |

Of 595 issued recommendations, 451 have a classifiable comparison. Unknown outcomes are excluded from each faster rate. Stay is compared with the supplied alternative. Switch is compared with the original Stay.

The uncertainty intervals reflect archived timing bounds. The table describes these two selected corridors and does not estimate performance across the subway system or an incremental advantage over raw MTA.

[Per-recommendation records and train traces](november-all-forecast-boarding.json) · [Frozen replay inputs](../../data/artifacts/november-two-corridor-replay.json.gz)
