# November fixed-Stay coverage interpretation

This input-only supplement explains availability in the frozen peak cohort.
It does not modify the input freeze, model, walks, route selection or outcome
rules. The source is `data/manifests/november-peak-inputs-frozen.json`, SHA256
`b73f9f149e4e77d2328e5dd5e5886028eebebc0c5c61d6b4760ad4ae4e94e484`.

## Weekday and weekend path availability

The analysis contains 13 weekdays, two Saturdays and three Sundays, with 44
departure checkpoints per corridor/date. The fixed Stay paths were selected by
Google on Friday, November 20, then held fixed for the historical analysis.
This creates an important weekend path limitation.

| Corridor and fixed Stay | Weekday usable forecasts / scheduled | Weekend usable forecasts / scheduled | All-date usable forecasts / scheduled |
|---|---:|---:|---:|
| Hayden LIC to Tandon, F | 572 / 572 | 9 / 220 | 581 / 792 |
| Grand Central to Borough Hall, 5 | 572 / 572 | 0 / 220 | 572 / 792 |
| Court Square to Times Square, 7 | 572 / 572 | 220 / 220 | 792 / 792 |
| Times Square to Borough Hall, 2 | 572 / 572 | 220 / 220 | 792 / 792 |
| Port Authority to Tandon, A | 572 / 572 | 220 / 220 | 792 / 792 |

All 431 checkpoints without a complete forecast occur on the five weekend
dates below. The recorded route reason is `NO_USABLE_CATCHABLE_TRAIN`: the
fixed path has no complete usable selected journey under the archived stop
pattern, timing and catchability rules. These rows must not be described as
zero delay or generic archive failures. They also do not establish that no
subway service or alternative route existed.

| Local date | Day type | Hayden F available / scheduled | Grand Central 5 available / scheduled |
|---|---|---:|---:|
| 2026-11-01 | Sunday | 0 / 44 | 0 / 44 |
| 2026-11-07 | Saturday | 0 / 44 | 0 / 44 |
| 2026-11-08 | Sunday | 0 / 44 | 0 / 44 |
| 2026-11-14 | Saturday | 6 / 44 | 0 / 44 |
| 2026-11-15 | Sunday | 3 / 44 | 0 / 44 |

## Final weekday reporting scope

After inspecting this input-only coverage, the user requested weekdays only.
The final report therefore uses November 2–6, 9–13 and 16–18: 13 weekdays,
2,860 checkpoints and 195 daily cells. All 2,860 weekday checkpoints have a
complete forecast. This note preserves the broader frozen input coverage for
audit only; no weekend outcomes contribute to the final report.

## Reading the delay tables

Forecast availability is only the first denominator. A forecast can still
lack a usable paired outcome because an endpoint is missing or excluded, or
because the selected train cannot actually be boarded under the inferred
endpoint timings. The completed delay tables separately show usable outcomes
and scheduled checkpoints.

The final 15 pooled corridor/period means retain the observed mix of the
thirteen weekdays; 195 daily cells preserve individual dates. Missing weekend
forecasts have not become zero-minute delays or been included in those means.
Even the available daily means have limited support, with at
most 16 morning, 12 midday and 16 evening departure checkpoints.

The fixed route is preserved rather than retrospectively replacing unavailable
weekend Stay paths with more convenient services. A future product can request
date-appropriate provider routes; that is a separate route-selection policy
and is not evaluated by these fixed-path statistics.

See [the weekday peak-delay report](november-weekday-peak-delays.md) and
[weekday daily cells](november-weekday-peak-delays-daily.csv) after outcome scoring.
