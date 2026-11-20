# Same-train forecast revision replay

This separate post-hoc exploratory search corrects the headway ambiguity in the earlier official-delay cohort. It uses the fixed October 25–31 five-minute clock grid and 5/10/15/30-minute reassessment lags, with no outcome-based case selection. Original models, thresholds and earlier reports are unchanged.

Origin: Court Square subway complex street entrance, Long Island City. Destination: Times Square, West 42nd Street at Seventh Avenue. The three supplied paths are 7, E and F with the already-declared walking assumptions; this is not an exhaustive citywide or historical Google route claim.

At T0 all three candidates have complete timing and comparison evidence, and the fastest raw-MTA route is fresh NORMAL. At T1 that route must still select the same physical train and stop pair as its best catchable train, while its absolute destination-arrival forecast has moved at least five minutes later. Remaining duration need not increase by five minutes: elapsed clock time is reported separately. Both decisions mean departing anew from the same street origin, still unboarded.

Official notices are displayed as context, but are not required for this direct feed-revision definition. A later forecast is evidence of forecast slippage, not independent proof of its cause or physical arrival. One representative per physical run is frozen using earliest T1 then earliest T0. All qualifying repeated pairs remain in the input artifact; none were selected using final outcomes.

Fixed pairs attempted: **8064**; qualifying pairs: **2**; distinct physical runs: **2**.

| Mode | Strict actions | Conditional timing actions | Scorable strict Switch | Strict gains / ties / losses | Unknown strict Switch |
|---|---|---|---:|---|---:|
| mta | {'STAY': 2} | {'STAY': 2} | 0 | 0 / 0 / 0 | 0 |
| time_profile | {'STAY': 2} | {'STAY': 2} | 0 | 0 / 0 / 0 | 0 |
| incident_profile | {'STAY': 2} | {'STAY': 2} | 0 | 0 / 0 / 0 | 0 |

The forecast-best non-Stay alternative is also compared even when the algorithm says STAY; hindsight does not choose this alternative.

| Mode | Comparable alternative pairs | Gains >3 min | Ties | Losses >3 min | Unknown |
|---|---:|---:|---:|---:|---:|
| mta | 0 | 0 | 0 | 0 | 2 |
| time_profile | 0 | 0 | 0 | 0 | 2 |
| incident_profile | 0 | 0 | 0 | 0 | 2 |

## All input-selected representatives

### 2026-10-28T12:55:00-04:00 — 7_times_square

T0 2026-10-28T12:45:00-04:00; lead 2.37 min; near tie: True. Planning interval 10.00 min. Same-train absolute arrival revision +7.45 min; remaining-duration change -2.55 min.

| Route | T0 MTA duration, min | T1 MTA duration, min |
|---|---:|---:|
| 7_times_square | 20.18 | 17.63 |
| e_times_square | 28.12 | 25.55 |
| f_times_square | 22.55 | 27.82 |

Same physical run `MTA:numbered:20261028:7:074100_7..S:`: departure forecast 2026-10-28T12:52:31-04:00 → 2026-10-28T12:59:58-04:00 (7.45 min); arrival forecast 2026-10-28T13:03:11-04:00 → 2026-10-28T13:10:38-04:00 (7.45 min).

| Mode | Strict / conditional action | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / STAY | e_times_square | 17.63 / 25.55 | unknown / 27.50 | unknown |
| time_profile | STAY / STAY | f_times_square | 17.44 / 20.28 | unknown / 21.20 | unknown |
| incident_profile | STAY / STAY | f_times_square | 16.33 / 20.28 | unknown / 21.20 | unknown |

As-of Stay service context: `{'ambiguous_scope': False, 'causes': ['UNKNOWN'], 'evidence_status': 'FRESH', 'incident_ids': [], 'severe_incident_ids': [], 'state': 'NORMAL'}`. Same pair remains qualified in 12/12 single-component +/-120-second walking variations.

### 2026-10-29T11:40:00-04:00 — 7_times_square

T0 2026-10-29T11:30:00-04:00; lead 3.17 min; near tie: False. Planning interval 10.00 min. Same-train absolute arrival revision +5.40 min; remaining-duration change -4.60 min.

| Route | T0 MTA duration, min | T1 MTA duration, min |
|---|---:|---:|
| 7_times_square | 20.85 | 16.25 |
| e_times_square | 24.02 | 24.83 |
| f_times_square | 27.32 | 27.52 |

Same physical run `MTA:numbered:20261029:7:066600_7..S:`: departure forecast 2026-10-29T11:38:11-04:00 → 2026-10-29T11:43:35-04:00 (5.40 min); arrival forecast 2026-10-29T11:48:51-04:00 → 2026-10-29T11:54:15-04:00 (5.40 min).

| Mode | Strict / conditional action | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / STAY | e_times_square | 16.25 / 24.83 | unknown / 28.87 | unknown |
| time_profile | STAY / STAY | e_times_square | 16.36 / 23.32 | unknown / 22.67 | unknown |
| incident_profile | STAY / STAY | e_times_square | 16.45 / 23.30 | unknown / 22.67 | unknown |

As-of Stay service context: `{'ambiguous_scope': False, 'causes': ['UNKNOWN'], 'evidence_status': 'FRESH', 'incident_ids': [], 'severe_incident_ids': [], 'state': 'NORMAL'}`. Same pair remains qualified in 9/12 single-component +/-120-second walking variations.

## Limits

Outcomes are screened final MTA prediction proxies plus authored walking, not independent actual passenger arrivals. Missed selected trains and missing endpoint evidence remain unknown. The test week was already explored, so this is diagnostic evidence, not a new untouched test or a general success rate. Exact selected trains, official notices, corrections, quality flags and all negative/unknown representatives are preserved in JSON.
