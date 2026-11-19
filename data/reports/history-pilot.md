# Historical Pilot Data Report

Generated: 2026-11-19T21:57:01.982918Z

This report describes data preparation, not model accuracy. Labels are inferred final-prediction proxies.

- Processed calendar dates: 2026-11-02, 2026-11-03, 2026-11-04, 2026-11-05, 2026-11-06, 2026-11-07, 2026-11-08, 2026-11-09, 2026-11-10, 2026-11-11, 2026-11-12, 2026-11-13, 2026-11-14, 2026-11-15
- Arrival examples: 8355779
- Arrival examples with usable proxy labels: 7623040
- Segment examples: 4647130
- Quality status: PREPARED_WITH_DOCUMENTED_PROXY_LIMITATIONS

| Decision-day type | All component rows | Usable proxy rows |
|---|---:|---:|
| SATURDAY | 1274427 | 1145687 |
| SUNDAY | 1192402 | 1054313 |
| WEEKDAY | 10536080 | 9492202 |

## Limitations

- Arrival and segment labels derive from final prediction journals, not physical ground truth.
- Vehicle-status checks use a different derivation of the same MTA source, not independent observations.
- Only configured target stations, routes, horizons and sampled collection times are included.
- Only two weekends are present; chronological validation contains weekdays only.
- No historical Google route predictions or defensible full passenger journey outcomes are supplied.
- Historical alert captures are content-deduplicated; old last-observed alerts do not establish fresh current alert state.
- No model has been trained and no prediction accuracy or realized time saving has been established.
