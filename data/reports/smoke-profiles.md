# October historical delay profiles

This report describes MTA final-prediction proxies, not physical passenger arrivals. The full-month descriptive profile must never be used to predict its own validation or test outcomes.

Requested month complete: **False**. Training-only profile seal: `a5c01a8346d24de9636725655fd8d743ce860e0c2d5a97f54d105a4e8acae016`.

Development representative observations: 20744; eligible: 15939. Monthly representative observations: 20744; eligible: 16283.

## Weekday morning, midday and evening endpoint profiles

Rows below use the 15–30 minute prediction horizon and retain segment, direction and weekday class. Mean positive delay averages max(error, 0) across all cases; it differs from the conditional late-only mean. These are endpoint ETA residuals for listed subway segments, not door-to-door journey averages. Unknown and disrupted service are included in these time-only descriptive groups, not relabeled normal. Events/days/incidents describe usable outcomes. Unknown labels include missing or ambiguous endpoint proxies; their denominator includes all independent forecast events in the same time group, before quality exclusion.

| Route | Segment | Day | Period | Events | Days | Incidents | Mean signed min | Mean positive min | P90 min | Unknown labels |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|

## Other weekday periods and separate weekend profiles

| Route | Segment | Day | Period | Events | Days | Incidents | Mean signed min | Mean positive min | P90 min | Unknown labels |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 127S → 232S | SUNDAY | AFTERNOON | 16 | 1 | 1 | 0.66 | 1.15 | 2.73 | 0/16 (0.0%) |
| 3 | 127S → 232S | SUNDAY | AFTERNOON | 12 | 1 | 0 | 0.26 | 0.87 | 2.65 | 1/13 (7.7%) |
| 2 | 127S → 232S | SUNDAY | EVENING_PEAK | 25 | 1 | 3 | 1.35 | 1.69 | 2.20 | 1/26 (3.8%) |
| 3 | 127S → 232S | SUNDAY | EVENING_PEAK | 24 | 1 | 1 | 1.29 | 1.54 | 3.41 | 2/26 (7.7%) |
| 2 | 127S → 232S | SUNDAY | LATE_EVENING | 18 | 1 | 2 | 2.06 | 2.08 | 5.56 | 1/19 (5.3%) |
| 3 | 127S → 232S | SUNDAY | LATE_EVENING | 16 | 1 | 0 | 2.35 | 2.38 | 4.62 | 1/17 (5.9%) |
| 2 | 127S → 232S | SUNDAY | LATE_MORNING | 7 | 1 | 0 | 0.17 | 0.40 | 1.10 | 0/7 (0.0%) |
| 3 | 127S → 232S | SUNDAY | LATE_MORNING | 6 | 1 | 0 | 0.03 | 0.41 | 1.07 | 1/7 (14.3%) |
| 2 | 127S → 232S | SUNDAY | MIDDAY | 24 | 1 | 0 | 0.58 | 1.07 | 2.46 | 0/24 (0.0%) |
| 3 | 127S → 232S | SUNDAY | MIDDAY | 18 | 1 | 0 | 0.35 | 0.79 | 2.02 | 1/19 (5.3%) |
| 2 | 127S → 232S | SUNDAY | MORNING_PEAK | 15 | 1 | 1 | 2.64 | 2.85 | 6.47 | 0/15 (0.0%) |
| 3 | 127S → 232S | SUNDAY | MORNING_PEAK | 11 | 1 | 0 | 1.92 | 2.12 | 4.97 | 0/11 (0.0%) |
| 2 | 127S → 232S | SUNDAY | OVERNIGHT | 17 | 1 | 0 | 5.51 | 5.57 | 12.98 | 2/19 (10.5%) |
| 4 | 631S → 423S | SUNDAY | AFTERNOON | 16 | 1 | 1 | -4.26 | 0.00 | -3.24 | 0/16 (0.0%) |
| 4 | 631S → 423S | SUNDAY | EVENING_PEAK | 27 | 1 | 1 | -4.40 | 0.00 | -3.17 | 3/30 (10.0%) |
| 4 | 631S → 423S | SUNDAY | LATE_EVENING | 20 | 1 | 1 | -1.59 | 0.37 | 1.05 | 0/20 (0.0%) |
| 4 | 631S → 423S | SUNDAY | LATE_MORNING | 7 | 1 | 2 | -3.71 | 0.34 | -0.56 | 0/7 (0.0%) |
| 4 | 631S → 423S | SUNDAY | MIDDAY | 24 | 1 | 2 | -3.77 | 0.03 | -1.21 | 0/24 (0.0%) |
| 4 | 631S → 423S | SUNDAY | MORNING_PEAK | 18 | 1 | 2 | -4.41 | 0.00 | -1.84 | 0/18 (0.0%) |
| 4 | 631S → 423S | SUNDAY | OVERNIGHT | 18 | 1 | 2 | 0.34 | 0.98 | 3.15 | 3/21 (14.3%) |
| 7 | 719S → 723S | SUNDAY | AFTERNOON | 17 | 1 | 1 | 7.31 | 7.33 | 11.01 | 1/18 (5.6%) |
| 7 | 719S → 725S | SUNDAY | AFTERNOON | 17 | 1 | 1 | 7.84 | 7.84 | 10.97 | 1/18 (5.6%) |
| 7 | 719S → 723S | SUNDAY | EVENING_PEAK | 31 | 1 | 2 | 10.00 | 10.00 | 14.98 | 7/38 (18.4%) |
| 7 | 719S → 725S | SUNDAY | EVENING_PEAK | 29 | 1 | 2 | 9.82 | 9.82 | 15.07 | 9/38 (23.7%) |
| 7 | 719S → 723S | SUNDAY | LATE_EVENING | 29 | 1 | 1 | 3.56 | 3.56 | 5.33 | 0/29 (0.0%) |
| 7 | 719S → 725S | SUNDAY | LATE_EVENING | 18 | 1 | 1 | 5.25 | 5.25 | 9.43 | 10/28 (35.7%) |
| 7 | 719S → 723S | SUNDAY | LATE_MORNING | 11 | 1 | 0 | 6.97 | 6.97 | 9.78 | 0/11 (0.0%) |
| 7 | 719S → 725S | SUNDAY | LATE_MORNING | 10 | 1 | 0 | 7.29 | 7.29 | 11.48 | 0/10 (0.0%) |
| 7 | 719S → 723S | SUNDAY | MIDDAY | 20 | 1 | 1 | 7.67 | 7.75 | 13.20 | 8/28 (28.6%) |
| 7 | 719S → 725S | SUNDAY | MIDDAY | 10 | 1 | 1 | 5.10 | 5.26 | 10.21 | 19/29 (65.5%) |
| 7 | 719S → 723S | SUNDAY | MORNING_PEAK | 24 | 1 | 0 | 7.05 | 7.05 | 13.28 | 7/31 (22.6%) |
| 7 | 719S → 725S | SUNDAY | MORNING_PEAK | 26 | 1 | 0 | 6.77 | 6.80 | 13.88 | 5/31 (16.1%) |
| 7 | 719S → 723S | SUNDAY | OVERNIGHT | 16 | 1 | 0 | 1.47 | 1.53 | 3.02 | 6/22 (27.3%) |
| 7 | 719S → 725S | SUNDAY | OVERNIGHT | 15 | 1 | 0 | 2.74 | 2.75 | 4.66 | 6/21 (28.6%) |
| A | A27S → A41S | SUNDAY | AFTERNOON | 10 | 1 | 2 | 5.02 | 5.02 | 7.82 | 2/13 (15.4%) |
| C | A27S → A41S | SUNDAY | AFTERNOON | 11 | 1 | 2 | 8.17 | 8.17 | 12.25 | 0/11 (0.0%) |
| A | A27S → A41S | SUNDAY | EVENING_PEAK | 21 | 1 | 2 | 4.88 | 4.88 | 7.00 | 4/25 (16.0%) |
| C | A27S → A41S | SUNDAY | EVENING_PEAK | 21 | 1 | 2 | 8.05 | 8.05 | 10.00 | 0/21 (0.0%) |
| A | A27S → A41S | SUNDAY | LATE_EVENING | 17 | 1 | 1 | 4.53 | 4.53 | 6.42 | 4/22 (18.2%) |
| C | A27S → A41S | SUNDAY | LATE_EVENING | 13 | 1 | 2 | 7.90 | 7.90 | 11.74 | 0/13 (0.0%) |
| A | A27S → A41S | SUNDAY | LATE_MORNING | 6 | 1 | 0 | 9.06 | 9.06 | 11.23 | 0/7 (0.0%) |
| C | A27S → A41S | SUNDAY | LATE_MORNING | 5 | 1 | 1 | 7.33 | 7.33 | 8.70 | 1/6 (16.7%) |
| A | A27S → A41S | SUNDAY | MIDDAY | 19 | 1 | 0 | 6.02 | 6.02 | 10.43 | 0/19 (0.0%) |
| C | A27S → A41S | SUNDAY | MIDDAY | 16 | 1 | 1 | 9.36 | 9.36 | 12.54 | 0/16 (0.0%) |
| A | A27S → A41S | SUNDAY | MORNING_PEAK | 19 | 1 | 1 | 3.20 | 3.34 | 8.02 | 0/19 (0.0%) |
| C | A27S → A41S | SUNDAY | MORNING_PEAK | 12 | 1 | 1 | 5.78 | 5.78 | 7.25 | 1/13 (7.7%) |
| A | A27S → A41S | SUNDAY | OVERNIGHT | 19 | 1 | 1 | 3.89 | 3.89 | 5.31 | 1/20 (5.0%) |
| R | G21S → R29S | SUNDAY | LATE_EVENING | 0 | 0 | 0 | unavailable | unavailable | unavailable | 0/1 (0.0%) |
| G | G22S → A42S | SUNDAY | AFTERNOON | 16 | 1 | 0 | 1.68 | 1.84 | 3.98 | 0/16 (0.0%) |
| G | G22S → A42S | SUNDAY | EVENING_PEAK | 29 | 1 | 0 | 0.59 | 1.01 | 2.52 | 0/29 (0.0%) |
| G | G22S → A42S | SUNDAY | LATE_EVENING | 18 | 1 | 0 | -0.38 | 0.46 | 1.72 | 1/19 (5.3%) |
| G | G22S → A42S | SUNDAY | LATE_MORNING | 6 | 1 | 0 | 2.33 | 2.60 | 7.47 | 1/7 (14.3%) |
| G | G22S → A42S | SUNDAY | MIDDAY | 22 | 1 | 0 | 2.58 | 2.66 | 7.21 | 4/27 (14.8%) |
| G | G22S → A42S | SUNDAY | MORNING_PEAK | 11 | 1 | 1 | 0.11 | 0.59 | 1.28 | 5/16 (31.2%) |
| G | G22S → A42S | SUNDAY | OVERNIGHT | 18 | 1 | 0 | 5.42 | 5.60 | 12.48 | 0/19 (0.0%) |
| N | R09S → R17S | SUNDAY | AFTERNOON | 10 | 1 | 0 | 2.46 | 2.71 | 5.21 | 0/10 (0.0%) |
| N | R09S → R17S | SUNDAY | EVENING_PEAK | 19 | 1 | 0 | 1.84 | 2.22 | 5.29 | 2/21 (9.5%) |
| N | R09S → R17S | SUNDAY | LATE_EVENING | 17 | 1 | 0 | 2.25 | 2.33 | 4.81 | 3/20 (15.0%) |
| N | R09S → R17S | SUNDAY | LATE_MORNING | 4 | 1 | 0 | 4.18 | 4.18 | 5.88 | 1/5 (20.0%) |
| N | R09S → R17S | SUNDAY | MIDDAY | 14 | 1 | 0 | 1.27 | 1.68 | 3.92 | 2/16 (12.5%) |
| N | R09S → R17S | SUNDAY | MORNING_PEAK | 21 | 1 | 0 | 0.91 | 1.36 | 2.70 | 1/22 (4.5%) |
| N | R09S → R17S | SUNDAY | OVERNIGHT | 20 | 1 | 1 | 2.48 | 2.65 | 6.57 | 0/20 (0.0%) |
| R | R17S → R29S | SUNDAY | AFTERNOON | 11 | 1 | 0 | 5.58 | 5.58 | 9.72 | 0/11 (0.0%) |
| R | R17S → R29S | SUNDAY | EVENING_PEAK | 18 | 1 | 0 | 5.25 | 5.25 | 8.09 | 0/19 (0.0%) |
| R | R17S → R29S | SUNDAY | LATE_EVENING | 15 | 1 | 1 | 4.46 | 4.46 | 6.47 | 0/16 (0.0%) |
| R | R17S → R29S | SUNDAY | LATE_MORNING | 6 | 1 | 0 | 2.75 | 2.79 | 6.07 | 0/6 (0.0%) |
| R | R17S → R29S | SUNDAY | MIDDAY | 11 | 1 | 1 | 5.74 | 5.74 | 9.90 | 4/15 (26.7%) |
| R | R17S → R29S | SUNDAY | MORNING_PEAK | 19 | 1 | 0 | 2.81 | 2.81 | 4.31 | 1/20 (5.0%) |
| R | R17S → R29S | SUNDAY | OVERNIGHT | 2 | 1 | 0 | 2.39 | 2.39 | 3.37 | 0/2 (0.0%) |

## Interpretation

- Each hierarchy group counts a physical component event only once, including broader fallback groups.
- Sparse severe groups require both the configured event count and independent incident count; fallback is explicit.
- Incident text classification is rule-based and may remain unknown; it does not establish physical disruption extent.
- Last-observed alerts are separate from fresh evidence. Missing alerts are not normal service.
- Training labels must have a confirmed receipt before the development cutoff; crossing trains and unplanned disruption/severe incident families are purged.
- Planned-only and unknown-only notices remain explicit context; independent-incident generalization is not claimed for those categories.
- Unusable, expired, missing, canceled and changed-schedule observations remain counted in source/quality reports.
