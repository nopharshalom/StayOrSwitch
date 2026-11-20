# Affected-route-as-Stay replay: validation

This is a **post-hoc supplemental case study**, requested after the original results. It changes the Stay reference only; the algorithm, selected trains, historical profiles, thresholds and outcomes remain unchanged. It does not replace the original fastest-MTA benchmark or establish general performance.

Selection uses contemporaneous official severe exposure, never outcomes or recommended savings. A separate input-only text audit verifies that severe wording applies to the selected leg's actual line and direction. Every confirmed route at every original primary checkpoint is retained, including stale alert evidence that must withhold formal advice. All 11 candidate variants remain in each comparison.

Selected: **71 affected route/checkpoint pairs**, **25 unique checkpoints**, **3 affecting incident families**.

The frozen classifier initially supplied 87 candidate pairs; 16 were excluded from the confirmed cohort because severe wording concerned another line or direction. The broader classifier summary remains in JSON. This input-only case qualification does not fix or change the frozen predictor.

| Mode | Scope | Switches | Scorable | Unknown | Gain >3 min | Tie | Loss >3 min |
|---|---|---:|---:|---:|---:|---:|---:|
| mta | strict_decision | 62 | 43 | 19 | 43 | 0 | 0 |
| mta | conditional_timing_decision | 71 | 46 | 25 | 46 | 0 | 0 |
| time_profile | strict_decision | 61 | 35 | 26 | 35 | 0 | 0 |
| time_profile | conditional_timing_decision | 70 | 37 | 33 | 37 | 0 | 0 |
| incident_profile | strict_decision | 61 | 33 | 28 | 33 | 0 | 0 |
| incident_profile | conditional_timing_decision | 70 | 35 | 35 | 35 | 0 | 0 |

A Switch requires at least five minutes of predicted savings. Outcome differences within +/-three minutes are ties. Strict and conditional results overlap; they must not be added. Counts are route/checkpoint pairs, not independent passengers or incidents.

Outcome evidence follows exactly the originally forecast-selected trains. Missing or unusable endpoint labels and missed selected departures/transfers leave the complete journey ETA unknown; a later train is never substituted using hindsight. A missed departure is a known catchability failure, not absence of all evidence. Outcomes are screened final MTA prediction proxies with authored walking assumptions, not independently observed journeys.

## Why some Switches cannot be scored

`incident_profile / strict_decision`: 28 unknown Switch pairs.

- `stay:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 10
- `stay:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 8
- `switch:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 16
- `switch:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 2

Known catchability failures (complete journey ETA still unknown):

- `stay:INITIAL_BOARDING_MISSED`: 8
- `stay:TRANSFER_MISSED`: 2
- `switch:INITIAL_BOARDING_MISSED`: 16

Endpoint quality flags (overlapping):

- `stay:alighting:MISSING_CSV_ARRIVAL`: 6
- `stay:alighting:MISSING_CSV_LABEL`: 6
- `stay:alighting:MISSING_STOP_PASSAGE_CONFIRMATION`: 6
- `stay:alighting:PREDICTED_ARRIVAL_AFTER_STOP_DISAPPEARANCE`: 2
- `stay:boarding:MISSING_CSV_DEPARTURE`: 6
- `stay:boarding:MISSING_CSV_LABEL`: 6
- `stay:boarding:MISSING_STOP_PASSAGE_CONFIRMATION`: 6
- `stay:boarding:PREDICTED_DEPARTURE_AFTER_STOP_DISAPPEARANCE`: 2
- `switch:alighting:CSV_SCHEDULE_CHANGED`: 2
- `switch:boarding:CSV_SCHEDULE_CHANGED`: 2

`incident_profile / conditional_timing_decision`: 35 unknown Switch pairs.

- `stay:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 11
- `stay:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 14
- `switch:INFERRED_DEPARTURE_BEFORE_PLATFORM_READY`: 16
- `switch:MISSING_OR_UNUSABLE_ENDPOINT_LABEL`: 2

Known catchability failures (complete journey ETA still unknown):

- `stay:INITIAL_BOARDING_MISSED`: 9
- `stay:TRANSFER_MISSED`: 2
- `switch:INITIAL_BOARDING_MISSED`: 16

Endpoint quality flags (overlapping):

- `stay:alighting:MISSING_CSV_ARRIVAL`: 10
- `stay:alighting:MISSING_CSV_LABEL`: 10
- `stay:alighting:MISSING_STOP_PASSAGE_CONFIRMATION`: 10
- `stay:alighting:PREDICTED_ARRIVAL_AFTER_STOP_DISAPPEARANCE`: 2
- `stay:boarding:MISSING_CSV_DEPARTURE`: 10
- `stay:boarding:MISSING_CSV_LABEL`: 10
- `stay:boarding:MISSING_STOP_PASSAGE_CONFIRMATION`: 10
- `stay:boarding:PREDICTED_DEPARTURE_AFTER_STOP_DISAPPEARANCE`: 4
- `switch:alighting:CSV_SCHEDULE_CHANGED`: 2
- `switch:boarding:CSV_SCHEDULE_CHANGED`: 2

## Input-selected examples

Examples are the earliest chronological route per affecting incident and route family; route ID breaks ties. Selection does not require an outcome or a successful Switch. Every selected pair remains in the full results.

### 2026-10-21T13:32:05.198000-04:00 — Stay `7_2`

Incident(s): lmm:alert:272837. Alert evidence: **FRESH**.

Official as-of notice: [1][2][3] trains are running with severe delays in both directions after we addressed a switch malfunction at Franklin St . [1][2][3] trains have resumed making scheduled stops in both directions.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 56.5 | 39.4 | 17.1 | unknown | UNKNOWN |
| time_profile | SWITCH / g_direct | SWITCH / g_direct | 57.5 | 37.5 | 20.0 | unknown | UNKNOWN |
| incident_profile | SWITCH / g_direct | SWITCH / g_direct | 57.5 | 37.5 | 20.0 | unknown | UNKNOWN |

### 2026-10-21T19:22:16.520000-04:00 — Stay `7_2`

Incident(s): lmm:alert:272891. Alert evidence: **FRESH**.

Official as-of notice: [7][7X] trains are running with severe delays in both directions after we moved a train that had its brakes activated at Hunters Point Av. [7] trains have resumed making scheduled stops between Manhattan and Queens.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / g_direct | SWITCH / g_direct | 57.1 | 37.7 | 19.3 | unknown | UNKNOWN |
| time_profile | SWITCH / g_direct | SWITCH / g_direct | 57.0 | 39.4 | 17.6 | unknown | UNKNOWN |
| incident_profile | SWITCH / g_direct | SWITCH / g_direct | 61.0 | 39.2 | 21.8 | unknown | UNKNOWN |

### 2026-10-21T19:22:16.520000-04:00 — Stay `7_4`

Incident(s): lmm:alert:272891. Alert evidence: **FRESH**.

Official as-of notice: [7][7X] trains are running with severe delays in both directions after we moved a train that had its brakes activated at Hunters Point Av. [7] trains have resumed making scheduled stops between Manhattan and Queens.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / g_direct | SWITCH / g_direct | 51.6 | 37.7 | 13.8 | 15.1 | MEANINGFUL_GAIN |
| time_profile | SWITCH / g_direct | SWITCH / g_direct | 56.1 | 39.4 | 16.8 | 17.7 | MEANINGFUL_GAIN |
| incident_profile | SWITCH / g_direct | SWITCH / g_direct | 55.9 | 39.2 | 16.7 | 17.7 | MEANINGFUL_GAIN |

### 2026-10-22T18:44:56.524000-04:00 — Stay `n_r`

Incident(s): lmm:alert:273047. Alert evidence: **FRESH**.

Official as-of notice: [N][R] trains are running with severe delays in both directions. [B][D][Q] trains are running with delays in both directions. [N] train service between 36 St (Bklyn) and Coney Island-Stillwell Av has resumed. [R] train service between 36 St (Bklyn) and Bay Ridge-95 St has resumed. What Happened? NYPD is conducted an investigation at Bay Ridge Av. While trains get back on schedule, consider these alternatives: For service to/from Coney Island-Stillwell Av, consider taking a [D][F][Q] train. For [N][R] service between 36 St and 59 St, take a B11, B63 or B37 bus. For [N] service between 59 St and Coney Island-Stillwell Av, take a B64 bus. For [R] service between 59 St and Bay Ridge-95 St, take a B63 or B70 bus. For connecting service between [N], [F], and [B][Q] trains along Kings Hwy, take a B82 or B82-SBS bus.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 67.1 | 39.3 | 27.8 | 28.4 | MEANINGFUL_GAIN |
| time_profile | SWITCH / f_direct | SWITCH / f_direct | 67.9 | 42.0 | 25.9 | 28.4 | MEANINGFUL_GAIN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 67.9 | 41.9 | 26.0 | 28.4 | MEANINGFUL_GAIN |

### 2026-10-22T18:44:56.524000-04:00 — Stay `r_direct`

Incident(s): lmm:alert:273047. Alert evidence: **FRESH**.

Official as-of notice: [N][R] trains are running with severe delays in both directions. [B][D][Q] trains are running with delays in both directions. [N] train service between 36 St (Bklyn) and Coney Island-Stillwell Av has resumed. [R] train service between 36 St (Bklyn) and Bay Ridge-95 St has resumed. What Happened? NYPD is conducted an investigation at Bay Ridge Av. While trains get back on schedule, consider these alternatives: For service to/from Coney Island-Stillwell Av, consider taking a [D][F][Q] train. For [N][R] service between 36 St and 59 St, take a B11, B63 or B37 bus. For [N] service between 59 St and Coney Island-Stillwell Av, take a B64 bus. For [R] service between 59 St and Bay Ridge-95 St, take a B63 or B70 bus. For connecting service between [N], [F], and [B][Q] trains along Kings Hwy, take a B82 or B82-SBS bus.

| Mode | Strict action / route | Conditional action / route | Predicted Stay min | Conditional chosen min | Predicted saving min | Proxy saving min | Outcome |
|---|---|---|---:|---:|---:|---:|---|
| mta | SWITCH / f_direct | SWITCH / f_direct | 67.1 | 39.3 | 27.8 | 28.4 | MEANINGFUL_GAIN |
| time_profile | SWITCH / f_direct | SWITCH / f_direct | 67.9 | 42.0 | 25.9 | 28.4 | MEANINGFUL_GAIN |
| incident_profile | SWITCH / f_direct | SWITCH / f_direct | 67.9 | 41.9 | 26.0 | 28.4 | MEANINGFUL_GAIN |

## Scope and artifacts

Only existing baseline checkpoint routes with a complete as-of selected journey can establish segment exposure; unavailable routes remain reported but cannot be assigned definite exposure from the cached records.

Severe-specific training support is unchanged and sparse; an incident-profile result may use time-profile fallback. The MTA mode shows how much switching is already supported by current feeds without historical correction. Different line names do not prove independent disruption exposure.

Full deterministic cases: `algo/local/october-affected-stay/validation-cases.jsonl.gz` (SHA256 `18f5d4620cddc18ec9428ced2fc277962386a15c5c7fb4765d19315f2998e8d8`).

Selection and code/input hashes were saved before supplemental scoring in `algo/reports/affected-stay-selection-frozen.json`. Original evaluation artifacts are unchanged.
