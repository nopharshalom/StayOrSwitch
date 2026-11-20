# Same-train forecast revision replay

This separate post-hoc exploratory search corrects the headway ambiguity in the earlier official-delay cohort. It uses the fixed October 25–31 five-minute clock grid and 5/10/15/30-minute reassessment lags, with no outcome-based case selection. Original models, thresholds and earlier reports are unchanged.

Origin: Grand Central street entrance at East 42nd Street and Lexington Avenue. Destination: Brooklyn Borough Hall street corner at Court Street and Joralemon Street. The four supplied paths are direct 4/5, 7 then 2/3, walk to Times Square then 2/3, and walk to Bryant Park then F to Jay Street and walk, with the already-declared walking assumptions; this is not an exhaustive citywide or historical Google route claim.

At T0 all four candidates have complete timing and comparison evidence, and the fastest raw-MTA route is fresh NORMAL. At T1 that route must still select the same physical train and stop pair as its best catchable train, while its absolute destination-arrival forecast has moved at least five minutes later. Remaining duration need not increase by five minutes: elapsed clock time is reported separately. Both decisions mean departing anew from the same street origin, still unboarded.

Official notices are displayed as context, but are not required for this direct feed-revision definition. A later forecast is evidence of forecast slippage, not independent proof of its cause or physical arrival. One representative per physical run is frozen using earliest T1 then earliest T0. All qualifying repeated pairs remain in the input artifact; none were selected using final outcomes.

Fixed pairs attempted: **8064**; qualifying pairs: **5**; distinct physical runs: **3**.

| Mode | Strict actions | Conditional timing actions | Scorable strict Switch | Strict gains / ties / losses | Unknown strict Switch |
|---|---|---|---:|---|---:|
| mta | {'STAY': 3} | {'STAY': 3} | 0 | 0 / 0 / 0 | 0 |
| time_profile | {'STAY': 3} | {'STAY': 3} | 0 | 0 / 0 / 0 | 0 |
| incident_profile | {'STAY': 3} | {'STAY': 3} | 0 | 0 / 0 / 0 | 0 |

The forecast-best non-Stay alternative is also compared even when the algorithm says STAY; hindsight does not choose this alternative.

| Mode | Comparable alternative pairs | Gains >3 min | Ties | Losses >3 min | Unknown |
|---|---:|---:|---:|---:|---:|
| mta | 2 | 0 | 0 | 2 | 1 |
| time_profile | 2 | 0 | 0 | 2 | 1 |
| incident_profile | 2 | 0 | 0 | 2 | 1 |

This is a separate OD expansion after the Court Square same-run cohort produced two unusable Stay outcomes. It retains all prior artifacts and uses identical selection thresholds and lags. This coverage-motivated extension is post-hoc; it is not a new untouched evaluation. Walking stress tests vary one access or egress component; transfer walks remain fixed.

## All input-selected representatives

### 2026-10-25T01:05:00-04:00 — lexington_direct

T0 2026-10-25T01:00:00-04:00; lead 12.28 min; near tie: False. Planning interval 5.00 min. Same-train absolute arrival revision +6.68 min; remaining-duration change 1.68 min.

| Route | T0 MTA duration, min | T1 MTA duration, min |
|---|---:|---:|
| lexington_direct | 37.00 | 38.68 |
| broadway_via_7 | 57.90 | 53.27 |
| walk_broadway | 57.90 | 53.27 |
| walk_f | 49.28 | 43.97 |

Same physical run `MTA:numbered:20261025:4:005400_4..S13X061:`: departure forecast 2026-10-25T01:13:00-04:00 → 2026-10-25T01:19:41-04:00 (6.68 min); arrival forecast 2026-10-25T01:35:00-04:00 → 2026-10-25T01:41:41-04:00 (6.68 min).

| Mode | Strict / conditional action | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / STAY | walk_f | 38.68 / 43.97 | 40.95 / 47.70 | -6.75 |
| time_profile | STAY / STAY | walk_f | 42.86 / 46.91 | 40.95 / 47.70 | -6.75 |
| incident_profile | STAY / STAY | walk_f | 41.86 / 46.91 | 40.95 / 47.70 | -6.75 |

As-of Stay service context: `{'ambiguous_scope': False, 'causes': ['UNKNOWN'], 'evidence_status': 'FRESH', 'incident_ids': [], 'severe_incident_ids': [], 'state': 'NORMAL'}`. Same pair remains qualified in 15/16 single-component +/-120-second walking variations.

### 2026-10-29T10:00:00-04:00 — lexington_direct

T0 2026-10-29T09:50:00-04:00; lead 9.57 min; near tie: False. Planning interval 10.00 min. Same-train absolute arrival revision +9.08 min; remaining-duration change -0.92 min.

| Route | T0 MTA duration, min | T1 MTA duration, min |
|---|---:|---:|
| lexington_direct | 29.00 | 28.08 |
| broadway_via_7 | 38.57 | 39.05 |
| walk_broadway | 38.57 | 39.05 |
| walk_f | 40.62 | 39.52 |

Same physical run `MTA:numbered:20261029:5:054700_5..S03R:`: departure forecast 2026-10-29T09:57:00-04:00 → 2026-10-29T10:06:05-04:00 (9.08 min); arrival forecast 2026-10-29T10:17:00-04:00 → 2026-10-29T10:26:05-04:00 (9.08 min).

| Mode | Strict / conditional action | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / STAY | broadway_via_7 | 28.08 / 39.05 | 25.63 / unknown | unknown |
| time_profile | STAY / STAY | broadway_via_7 | 27.70 / 39.37 | 25.63 / unknown | unknown |
| incident_profile | STAY / STAY | broadway_via_7 | 29.63 / 39.31 | 25.63 / unknown | unknown |

As-of Stay service context: `{'ambiguous_scope': False, 'causes': ['POLICE'], 'evidence_status': 'FRESH', 'incident_ids': ['lmm:alert:273981'], 'severe_incident_ids': [], 'state': 'DISRUPTION'}`. Same pair remains qualified in 16/16 single-component +/-120-second walking variations.

### 2026-10-29T15:20:00-04:00 — lexington_direct

T0 2026-10-29T15:10:00-04:00; lead 14.27 min; near tie: False. Planning interval 10.00 min. Same-train absolute arrival revision +8.42 min; remaining-duration change -1.58 min.

| Route | T0 MTA duration, min | T1 MTA duration, min |
|---|---:|---:|
| lexington_direct | 27.30 | 25.72 |
| broadway_via_7 | 45.00 | 43.00 |
| walk_broadway | 45.00 | 39.02 |
| walk_f | 41.57 | 38.13 |

Same physical run `MTA:numbered:20261029:4:087750_4..S06R:`: departure forecast 2026-10-29T15:15:48-04:00 → 2026-10-29T15:24:13-04:00 (8.42 min); arrival forecast 2026-10-29T15:35:18-04:00 → 2026-10-29T15:43:43-04:00 (8.42 min).

| Mode | Strict / conditional action | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / STAY | walk_f | 25.72 / 38.13 | 24.33 / 42.05 | -17.72 |
| time_profile | STAY / STAY | walk_f | 25.11 / 36.70 | 24.33 / 39.08 | -14.75 |
| incident_profile | STAY / STAY | walk_f | 24.97 / 36.70 | 24.33 / 39.08 | -14.75 |

As-of Stay service context: `{'ambiguous_scope': False, 'causes': ['UNKNOWN'], 'evidence_status': 'FRESH', 'incident_ids': [], 'severe_incident_ids': [], 'state': 'NORMAL'}`. Same pair remains qualified in 15/16 single-component +/-120-second walking variations.

## Limits

Outcomes are screened final MTA prediction proxies plus authored walking, not independent actual passenger arrivals. Missed selected trains and missing endpoint evidence remain unknown. The test week was already explored, so this is diagnostic evidence, not a new untouched test or a general success rate. Exact selected trains, official notices, corrections, quality flags and all negative/unknown representatives are preserved in JSON.
