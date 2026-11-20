# Observable severe-Switch illustrations

These are **outcome-selected illustrations**, not a new evaluation population. For each of the four test incidents, show the earliest strict incident-profile Switch with comparable proxy outcomes; when none exists, retain the earliest input-selected case. This rule makes the examples readable and must not be used to claim a success rate. Original chronological input-selected examples remain in the full test report.

Full confirmed test population: **79 route/checkpoint pairs, 29 checkpoints, four incidents**. There were **56 strict Switch recommendations: 13 scorable and 43 unknown**, plus 23 abstentions. Several pairs belong to the same incident or selected trains.

| New York time | Official incident | Stay | Incident-profile Switch | Predicted Stay / Switch, min | Predicted saving, min | Proxy Stay / Switch, min | Proxy saving, min |
|---|---|---|---|---:|---:|---:|---:|
| 2026-10-26T15:41:22.744000-04:00 | lmm:alert:273546 | n_r | f_direct | 64.0 / 42.4 | 21.6 | 64.1 / 48.3 | 15.8 |
| 2026-10-28T19:25:28.579000-04:00 | lmm:alert:273870 | 7_5 | f_direct | 68.8 / 43.2 | 25.6 | 73.9 / 44.1 | 29.9 |
| 2026-10-30T07:19:15.544000-04:00 | lmm:alert:274118 | 7_2 | f_direct | 52.1 / 40.3 | 11.7 | unknown / unknown | unknown |
| 2026-10-30T10:29:25.644000-04:00 | lmm:alert:274164 | w_r | g_direct | 67.5 / 44.4 | 23.1 | 65.5 / 43.8 | 21.8 |

## Raw MTA comparison

These affected routes can already be much slower in the current feed. A successful Switch during an official severe notice does not establish that historical corrections added value.

| New York time | Raw-MTA Switch | Raw-MTA predicted Stay / Switch, min | Raw-MTA predicted saving, min | Raw-MTA proxy saving, min |
|---|---|---:|---:|---:|
| 2026-10-26T15:41:22.744000-04:00 | g_direct | 62.1 / 39.6 | 22.5 | 24.5 |
| 2026-10-28T19:25:28.579000-04:00 | f_direct | 68.4 / 40.6 | 27.8 | 29.9 |
| 2026-10-30T07:19:15.544000-04:00 | f_direct | 51.8 / 38.9 | 12.8 | unknown |
| 2026-10-30T10:29:25.644000-04:00 | f_direct | 66.6 / 42.2 | 24.4 | 21.0 |

## Official context and unknown evidence

### 2026-10-26T15:41:22.744000-04:00 — lmm:alert:273546

Selection: `EARLIEST_STRICT_SWITCH_WITH_COMPARABLE_OUTCOMES_FOR_INCIDENT`. Official evidence: `FRESH`.

[N][R][W] trains are running with severe delays in both directions. [Q] trains are running with delays in both directions. What Happened? FDNY responded to a report of smoke near Lexington Av/59 St.


### 2026-10-28T19:25:28.579000-04:00 — lmm:alert:273870

Selection: `EARLIEST_STRICT_SWITCH_WITH_COMPARABLE_OUTCOMES_FOR_INCIDENT`. Official evidence: `FRESH`.

[2][5] trains are running with severe delays in both directions after we replaced a broken rail near 3 Av/149 St.


### 2026-10-30T07:19:15.544000-04:00 — lmm:alert:274118

Selection: `EARLIEST_INPUT_SELECTED_CASE_FOR_INCIDENT_WITH_NO_COMPARABLE_STRICT_SWITCH`. Official evidence: `FRESH`.

[7][7X] trains are running with severe delays in both directions after NYPD removed an unauthorized person from the tracks near 46 St-Bliss St. [7][7X] trains have resumed making all regular station stops. While we get trains back on schedule, consider use [E][F][M][R][W] trains instead.

- Stay: `MISSING_OR_UNUSABLE_ENDPOINT_LABEL`; flags: `{"alighting": [], "boarding": ["PREDICTED_DEPARTURE_AFTER_STOP_DISAPPEARANCE"]}`.
- Switch: `MISSING_OR_UNUSABLE_ENDPOINT_LABEL`; flags: `{"alighting": ["CSV_SCHEDULE_CHANGED", "CSV_SCHEDULE_REWRITTEN"], "boarding": ["CSV_SCHEDULE_CHANGED", "CSV_SCHEDULE_REWRITTEN"]}`.

### 2026-10-30T10:29:25.644000-04:00 — lmm:alert:274164

Selection: `EARLIEST_STRICT_SWITCH_WITH_COMPARABLE_OUTCOMES_FOR_INCIDENT`. Official evidence: `FRESH`.

[N][W] trains are running with severe delays in both directions. [R] train are running with delays in both directions. What Happened? NYPD assisted with someone being disruptive and we removed a train car in need of cleaning from service at 5 Av/59 St. Uptown [N][R][W] trains have resumed making scheduled stops between Manhattan and Queens. Travel Alternatives: For service from Manhattan to Queens, take [7][E][F][M][R] trains instead.

[N][W] trains are running with severe delays in both directions. [R] train are running with delays in both directions. What Happened? NYPD assisted with someone being disruptive and we removed a train car in need of cleaning from service at 5 Av/59 St. Uptown [N][R][W] trains have resumed making scheduled stops between Manhattan and Queens. Travel Alternatives: For service from Manhattan to Queens, take [7][E][F][M][R] trains instead.


All times are remaining door-to-door durations under authored walking assumptions. Outcomes are screened final MTA prediction proxies, not independently observed passenger arrivals. A missed selected departure is a known catchability failure; the complete replacement journey remains unknown.

Source cases: `algo/local/october-affected-stay/test-cases.jsonl.gz` (SHA256 `c1dbdbc2dcd3abd688eda794448fa6e91714fb350315a4de698e91af84fbc4f0`). No frozen predictions, thresholds, profiles, original examples, or evaluation population were changed.
