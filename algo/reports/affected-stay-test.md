# Affected-route-as-Stay replay: test

This is a **post-hoc supplemental case study**, requested after the original results. It changes the Stay reference only; the algorithm, selected trains, historical profiles, thresholds and outcomes remain unchanged. It does not replace the original fastest-MTA benchmark or establish general performance.

Selection uses contemporaneous official severe exposure, never outcomes or recommended savings. A separate input-only text audit verifies that severe wording applies to the selected leg's actual line and direction. Every confirmed route at every original primary checkpoint is retained, including stale alert evidence that must withhold formal advice. All 11 candidate variants remain in each comparison.

Selected: **79 affected route/checkpoint pairs**, **29 unique checkpoints**, **4 affecting incident families**.

The frozen classifier initially supplied 85 candidate pairs; 6 were excluded from the confirmed cohort because severe wording concerned another line or direction. The broader classifier summary remains in JSON. This input-only case qualification does not fix or change the frozen predictor.

| Mode | Scope | Switches | Scorable | Unknown | Gain >3 min | Tie | Loss >3 min |
|---|---|---:|---:|---:|---:|---:|---:|
| mta | strict_decision | 56 | 21 | 35 | 21 | 0 | 0 |
| mta | conditional_timing_decision | 79 | 34 | 45 | 34 | 0 | 0 |
| time_profile | strict_decision | 55 | 20 | 35 | 20 | 0 | 0 |
| time_profile | conditional_timing_decision | 78 | 29 | 49 | 29 | 0 | 0 |
| incident_profile | strict_decision | 56 | 13 | 43 | 13 | 0 | 0 |
| incident_profile | conditional_timing_decision | 79 | 22 | 57 | 22 | 0 | 0 |

A Switch requires at least five minutes of predicted savings. Outcome differences within +/-three minutes are ties. Strict and conditional results overlap; they must not be added. Counts are route/checkpoint pairs, not independent passengers or incidents.

Outcome evidence follows exactly the originally forecast-selected trains. Missing or unusable endpoint labels and missed selected departures/transfers leave the complete journey ETA unknown; a later train is never substituted using hindsight. A missed departure is a known catchability failure, not absence of all evidence. Outcomes are screened final MTA prediction proxies with authored walking assumptions, not independently observed journeys.

## Why some Switches cannot be scored

`incident_profile / strict_decision`: 43 unknown Switch pairs.

- `stay:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 4
- `stay:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 22
- `switch:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 13
- `switch:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 12

Known catchability failures (complete journey ETA still unknown):

- `stay:INITIAL_BOARDING_MISSED`: 3
- `stay:TRANSFER_MISSED`: 1
- `switch:INITIAL_BOARDING_MISSED`: 13

Endpoint quality flags (overlapping):

- `stay:alighting:MISSING_CSV_ARRIVAL`: 8
- `stay:alighting:MISSING_CSV_LABEL`: 8
- `stay:alighting:MISSING_STOP_PASSAGE_CONFIRMATION`: 8
- `stay:alighting:PREDICTED_ARRIVAL_AFTER_STOP_DISAPPEARANCE`: 7
- `stay:boarding:MISSING_CSV_DEPARTURE`: 8
- `stay:boarding:MISSING_CSV_LABEL`: 8
- `stay:boarding:MISSING_STOP_PASSAGE_CONFIRMATION`: 8
- `stay:boarding:PREDICTED_DEPARTURE_AFTER_STOP_DISAPPEARANCE`: 12
- `switch:alighting:CSV_SCHEDULE_CHANGED`: 12
- `switch:alighting:CSV_SCHEDULE_REWRITTEN`: 10
- `switch:alighting:MISSING_CSV_ARRIVAL`: 6
- `switch:alighting:MISSING_CSV_LABEL`: 6
- `switch:alighting:MISSING_STOP_PASSAGE_CONFIRMATION`: 6
- `switch:boarding:CSV_SCHEDULE_CHANGED`: 12
- `switch:boarding:CSV_SCHEDULE_REWRITTEN`: 10
- `switch:boarding:MISSING_CSV_DEPARTURE`: 6
- `switch:boarding:MISSING_CSV_LABEL`: 6
- `switch:boarding:MISSING_STOP_PASSAGE_CONFIRMATION`: 6

`incident_profile / conditional_timing_decision`: 57 unknown Switch pairs.

- `stay:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 5
- `stay:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 23
- `switch:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 20
- `switch:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 18

Known catchability failures (complete journey ETA still unknown):

- `stay:INITIAL_BOARDING_MISSED`: 4
- `stay:TRANSFER_MISSED`: 1
- `switch:INITIAL_BOARDING_MISSED`: 20

Endpoint quality flags (overlapping):

- `stay:alighting:MISSING_CSV_ARRIVAL`: 8
- `stay:alighting:MISSING_CSV_LABEL`: 8
- `stay:alighting:MISSING_STOP_PASSAGE_CONFIRMATION`: 8
- `stay:alighting:PREDICTED_ARRIVAL_AFTER_STOP_DISAPPEARANCE`: 8
- `stay:boarding:MISSING_CSV_DEPARTURE`: 8
- `stay:boarding:MISSING_CSV_LABEL`: 8
- `stay:boarding:MISSING_STOP_PASSAGE_CONFIRMATION`: 8
- `stay:boarding:PREDICTED_DEPARTURE_AFTER_STOP_DISAPPEARANCE`: 12
- `switch:alighting:CSV_SCHEDULE_CHANGED`: 18
- `switch:alighting:CSV_SCHEDULE_REWRITTEN`: 10
- `switch:alighting:MISSING_CSV_ARRIVAL`: 6
- `switch:alighting:MISSING_CSV_LABEL`: 6
- `switch:alighting:MISSING_STOP_PASSAGE_CONFIRMATION`: 6
- `switch:boarding:CSV_SCHEDULE_CHANGED`: 18
- `switch:boarding:CSV_SCHEDULE_REWRITTEN`: 10
- `switch:boarding:MISSING_CSV_DEPARTURE`: 6
- `switch:boarding:MISSING_CSV_LABEL`: 6
- `switch:boarding:MISSING_STOP_PASSAGE_CONFIRMATION`: 6

## Input-selected examples

Examples are the earliest chronological route per affecting incident and route family; route ID breaks ties. Selection does not require an outcome or a successful Switch. Every selected pair remains in the full results.

### 2026-10-26T15:06:22.744000-04:00 — Stay `n_r`

Incident(s): lmm:alert:273546. Alert evidence: **FRESH**.

Official as-of notice: [N][R][W] trains are running with severe delays in both directions. [Q] trains are running with delays in both directions. What Happened? FDNY responded to a report of smoke near Lexington Av/59 St.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / g_direct | SWITCH / g_direct | 61.1 | 38.6 | 22.5 | 19.9 | MEANINGFUL_GAIN |
| time_profile | SWITCH / g_direct | SWITCH / g_direct | 63.0 | 40.5 | 22.6 | 19.9 | MEANINGFUL_GAIN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 63.0 | 38.8 | 24.2 | unknown | UNKNOWN |

### 2026-10-26T15:06:22.744000-04:00 — Stay `r_direct`

Incident(s): lmm:alert:273546. Alert evidence: **FRESH**.

Official as-of notice: [N][R][W] trains are running with severe delays in both directions. [Q] trains are running with delays in both directions. What Happened? FDNY responded to a report of smoke near Lexington Av/59 St.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / g_direct | SWITCH / g_direct | 61.1 | 38.6 | 22.5 | 19.9 | MEANINGFUL_GAIN |
| time_profile | SWITCH / g_direct | SWITCH / g_direct | 63.0 | 40.5 | 22.6 | 19.9 | MEANINGFUL_GAIN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 63.0 | 38.8 | 24.2 | unknown | UNKNOWN |

### 2026-10-28T19:00:28.579000-04:00 — Stay `7_2`

Incident(s): lmm:alert:273870. Alert evidence: **FRESH**.

Official as-of notice: [2][5] trains are running with severe delays in both directions after we replaced a broken rail near 3 Av/149 St.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 53.0 | 39.8 | 13.2 | unknown | UNKNOWN |
| time_profile | SWITCH / f_direct | SWITCH / f_direct | 56.0 | 38.3 | 17.7 | unknown | UNKNOWN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 56.0 | 38.2 | 17.8 | unknown | UNKNOWN |

### 2026-10-28T19:00:28.579000-04:00 — Stay `7_5`

Incident(s): lmm:alert:273870. Alert evidence: **FRESH**.

Official as-of notice: [2][5] trains are running with severe delays in both directions after we replaced a broken rail near 3 Av/149 St.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 59.8 | 39.8 | 20.0 | unknown | UNKNOWN |
| time_profile | SWITCH / f_direct | SWITCH / f_direct | 60.3 | 38.3 | 21.9 | unknown | UNKNOWN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 60.3 | 38.2 | 22.1 | unknown | UNKNOWN |

### 2026-10-30T07:19:15.544000-04:00 — Stay `7_2`

Incident(s): lmm:alert:274118. Alert evidence: **FRESH**.

Official as-of notice: [7][7X] trains are running with severe delays in both directions after NYPD removed an unauthorized person from the tracks near 46 St-Bliss St. [7][7X] trains have resumed making all regular station stops. While we get trains back on schedule, consider use [E][F][M][R][W] trains instead.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 51.8 | 38.9 | 12.8 | unknown | UNKNOWN |
| time_profile | SWITCH / f_direct | SWITCH / f_direct | 52.5 | 41.9 | 10.5 | unknown | UNKNOWN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 52.1 | 40.3 | 11.7 | unknown | UNKNOWN |

### 2026-10-30T07:19:15.544000-04:00 — Stay `7_4`

Incident(s): lmm:alert:274118. Alert evidence: **FRESH**.

Official as-of notice: [7][7X] trains are running with severe delays in both directions after NYPD removed an unauthorized person from the tracks near 46 St-Bliss St. [7][7X] trains have resumed making all regular station stops. While we get trains back on schedule, consider use [E][F][M][R][W] trains instead.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 51.5 | 38.9 | 12.5 | unknown | UNKNOWN |
| time_profile | STAY / 7_4 | STAY / 7_4 | 46.6 | 46.6 | 0.0 | unknown | UNKNOWN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 46.8 | 40.3 | 6.4 | unknown | UNKNOWN |

### 2026-10-30T10:29:25.644000-04:00 — Stay `n_r`

Incident(s): lmm:alert:274164. Alert evidence: **FRESH**.

Official as-of notice: [N][W] trains are running with severe delays in both directions. [R] train are running with delays in both directions. What Happened? NYPD assisted with someone being disruptive and we removed a train car in need of cleaning from service at 5 Av/59 St. Uptown [N][R][W] trains have resumed making scheduled stops between Manhattan and Queens. Travel Alternatives: For service from Manhattan to Queens, take [7][E][F][M][R] trains instead.

Official as-of notice: [N][W] trains are running with severe delays in both directions. [R] train are running with delays in both directions. What Happened? NYPD assisted with someone being disruptive and we removed a train car in need of cleaning from service at 5 Av/59 St. Uptown [N][R][W] trains have resumed making scheduled stops between Manhattan and Queens. Travel Alternatives: For service from Manhattan to Queens, take [7][E][F][M][R] trains instead.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 66.6 | 42.2 | 24.4 | unknown | UNKNOWN |
| time_profile | SWITCH / f_direct | SWITCH / f_direct | 75.0 | 44.4 | 30.7 | unknown | UNKNOWN |
| incident_profile | SWITCH / g_direct | SWITCH / g_direct | 75.0 | 44.4 | 30.6 | unknown | UNKNOWN |

## Scope and artifacts

Only existing baseline checkpoint routes with a complete as-of selected journey can establish segment exposure; unavailable routes remain reported but cannot be assigned definite exposure from the cached records.

Severe-specific training support is unchanged and sparse; an incident-profile result may use time-profile fallback. The MTA mode shows how much switching is already supported by current feeds without historical correction. Different line names do not prove independent disruption exposure.

Full deterministic cases: `algo/local/october-affected-stay/test-cases.jsonl.gz` (SHA256 `c1dbdbc2dcd3abd688eda794448fa6e91714fb350315a4de698e91af84fbc4f0`).

Selection and code/input hashes were saved before supplemental scoring in `algo/reports/affected-stay-selection-frozen.json`. Original evaluation artifacts are unchanged.
