# Clear-default route before delay: observed comparison

This is a descriptive appendix to the frozen exploratory test, not a new cohort or a retuned algorithm. The predeclared baseline near-tie boundary is three minutes. All 31 cases remain in the original report; this appendix separates the 24 clearly fastest Lexington-route cases from seven F cases whose initial lead was only 17 seconds.

The October 26 positive comparison below is a later-departure counterfactual, not proof that the original fastest train became delayed. A separate raw-input audit shows that the originally selected 4 train `017800_4..S13X061` became uncatchable as planning time advanced under the three-minute access assumption. The later selected train `019800_4..S13X061` was already present at T0, and both its departure and arrival forecasts improved by 53 seconds by T1. The apparent 11.84-minute route deterioration mixes a missed earlier train and headway; a separate same-physical-train revision experiment is needed for the stronger delay claim. Evidence: `algo/reports/preincident-brooklyn-headway-audit.json`.

Origin: Grand Central at East 42nd Street / Lexington Avenue. Destination: Borough Hall at Court Street / Joralemon Street. Supplied candidates are direct 4-or-5; 7 then 2-or-3; walk to Times Square then 2-or-3; and walk to Bryant Park, F to Jay Street, then walk. Same-platform 4/5 choices are one route, not a manufactured Switch opportunity.

Walking times are authored research assumptions: direct 4/5 has three minutes of access and two minutes of egress; the F option has ten minutes of access and eight minutes of egress. Catchability, including whether the earlier direct train can still be boarded, depends on these assumptions.

The state is unboarded at each cutoff. Reassessment starts a new journey from the same origin; elapsed planning time is not added to either route. These are ordinary official delay notices, not all severe events. Outcome durations use screened final MTA predictions plus authored walking, not independent passenger observations.

## Decision results by predeclared baseline group

| Group | Cases | Incidents | Mode | Strict Switch | Scorable Switch | Gains | Ties | Losses | Unknown Switch |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| clear_default | 24 | 10 | mta | 0 | 0 | 0 | 0 | 0 | 0 |
| clear_default | 24 | 10 | time_profile | 2 | 2 | 0 | 0 | 2 | 0 |
| clear_default | 24 | 10 | incident_profile | 0 | 0 | 0 | 0 | 0 | 0 |
| near_tie | 7 | 1 | mta | 4 | 0 | 0 | 0 | 0 | 4 |
| near_tie | 7 | 1 | time_profile | 4 | 1 | 0 | 0 | 1 | 3 |
| near_tie | 7 | 1 | incident_profile | 4 | 1 | 0 | 0 | 1 | 3 |

## Would the forecast-best alternative actually help?

This comparison is made even when the algorithm says STAY. The alternative is selected by its forecast, never by its later outcome. A separate hindsight best-known alternative is retained only as a diagnostic in JSON.

| Group | Mode | Comparable | Gains >3 min | Ties | Losses >3 min | Unknown | Meaningful gains missed by strict STAY |
|---|---|---:|---:|---:|---:|---:|---:|
| clear_default | mta | 19 | 3 | 1 | 15 | 5 | 2 |
| clear_default | time_profile | 14 | 3 | 0 | 11 | 10 | 3 |
| clear_default | incident_profile | 10 | 2 | 0 | 8 | 14 | 2 |
| near_tie | mta | 0 | 0 | 0 | 0 | 7 | 0 |
| near_tie | time_profile | 1 | 0 | 0 | 1 | 6 | 0 |
| near_tie | incident_profile | 1 | 0 | 0 | 1 | 6 | 0 |

The two clear-default incident-profile gains come from one incident and the same selected 4/F train pair at two checkpoints. They are one repeated opportunity, not two independent successes. The algorithm said STAY at both, so they are missed opportunities rather than validated successful recommendations.

## Observable illustrations

Earliest comparable incident-profile Stay versus forecast-best alternative per clear-default incident, without filtering gains, losses or decisions. These are outcome-selected illustrations.

### 2026-10-25T02:32:32.704000-04:00

Incident lmm:alert:273391. Anchor 2026-10-25T02:27:31-04:00. First recorded problem boundary 2026-10-25T02:32:31-04:00; first problem receipt 2026-10-25T02:32:32.704000-04:00. Planning interval 5.03 minutes. Initial winner lead 16.92 minutes.

| Route | Before-problem MTA duration, min |
|---|---:|
| lexington_direct | 29.03 |
| broadway_via_7 | 70.57 |
| walk_broadway | 54.40 |
| walk_f | 45.95 |

Stay's unmodified remaining duration deteriorated by 15.42 minutes. Components (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 925.2960000038147, "walking_seconds": 0.0}`.

| Mode | Strict decision | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / lexington_direct | walk_f | 44.45 / 40.07 | 44.40 / 47.95 | -3.55 |
| time_profile | SWITCH / walk_f | walk_f | 48.64 / 43.02 | 44.40 / 47.95 | -3.55 |
| incident_profile | STAY / lexington_direct | walk_f | 46.67 / 43.02 | 44.40 / 47.95 | -3.55 |

The baseline and reassessment select different MTA trains: `MTA:numbered:20261025:4:013400_4..S13X061:` becomes `MTA:numbered:20261025:4:015400_4..S13X061:`. The duration increase therefore includes a changed catchable train/headway; it is not the same vehicle becoming that many minutes late, and the contemporaneous official delay does not establish that it caused the full increase.

Official as-of notice: Downtown [4][6] trains are running with delays after a work train proceeded through Manhattan.

Exact incident-profile proxy train evidence:

- `lexington_direct` / `MTA:numbered:20261025:4:015400_4..S13X061:`: platform-ready 2026-10-25T02:35:32.704000-04:00, inferred departure 2026-10-25T02:51:25-04:00, inferred station arrival 2026-10-25T03:14:57-04:00.
- `walk_f` / `MTA:bdfm:20261025:F:012300_F..S:02%3A03%3A00`: platform-ready 2026-10-25T02:42:32.704000-04:00, inferred departure 2026-10-25T02:54:22-04:00, inferred station arrival 2026-10-25T03:12:30-04:00.

Original winner remains fastest in 18/18 single-walk perturbations; this tests +/-two minutes of an access, transfer, or egress component. Exact trips and outcome quality remain in the linked JSON.

### 2026-10-26T03:21:00.539000-04:00

Incident lmm:alert:273480. Anchor 2026-10-26T03:14:59-04:00. First recorded problem boundary 2026-10-26T03:15:59-04:00; first problem receipt 2026-10-26T03:16:00.539000-04:00. Planning interval 6.03 minutes. Initial winner lead 15.92 minutes.

| Route | Before-problem MTA duration, min |
|---|---:|
| lexington_direct | 29.77 |
| broadway_via_7 | 67.70 |
| walk_broadway | 45.68 |
| walk_f | 47.28 |

Stay's unmodified remaining duration deteriorated by 11.84 minutes. Components (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 710.4609999656677, "walking_seconds": 0.0}`.

| Mode | Strict decision | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / lexington_direct | walk_f | 41.61 / 42.46 | 46.96 / 39.74 | 7.22 |
| time_profile | STAY / lexington_direct | walk_f | 42.79 / 45.40 | 46.96 / 39.74 | 7.22 |
| incident_profile | STAY / lexington_direct | walk_f | 45.69 / 45.40 | 46.96 / 39.74 | 7.22 |

The baseline and reassessment select different MTA trains: `MTA:numbered:20261026:4:017800_4..S13X061:` becomes `MTA:numbered:20261026:4:019800_4..S13X061:`. The duration increase therefore includes a changed catchable train/headway; it is not the same vehicle becoming that many minutes late, and the contemporaneous official delay does not establish that it caused the full increase.

Official as-of notice: [4] trains are delayed in both directions while we investigate why a train's brakes activated near Bowling Green.

Exact incident-profile proxy train evidence:

- `lexington_direct` / `MTA:numbered:20261026:4:019800_4..S13X061:`: platform-ready 2026-10-26T03:24:00.539000-04:00, inferred departure 2026-10-26T03:34:49-04:00, inferred station arrival 2026-10-26T04:05:58-04:00.
- `walk_f` / `MTA:bdfm:20261026:F:015950_F..S:02%3A41%3A45`: platform-ready 2026-10-26T03:31:00.539000-04:00, inferred departure 2026-10-26T03:35:25-04:00, inferred station arrival 2026-10-26T03:52:45-04:00.

Original winner remains fastest in 17/18 single-walk perturbations; this tests +/-two minutes of an access, transfer, or egress component. Exact trips and outcome quality remain in the linked JSON.

### 2026-10-28T16:49:55.639000-04:00

Incident lmm:alert:273870. Anchor 2026-10-28T15:58:53-04:00. First recorded problem boundary 2026-10-28T15:59:53-04:00; first problem receipt 2026-10-28T15:59:55.639000-04:00. Planning interval 51.04 minutes. Initial winner lead 12.25 minutes.

| Route | Before-problem MTA duration, min |
|---|---:|
| lexington_direct | 25.58 |
| broadway_via_7 | 37.83 |
| walk_broadway | 41.98 |
| walk_f | 38.68 |

Stay's unmodified remaining duration deteriorated by 5.09 minutes. Components (seconds): `{"riding_seconds": 90.0, "waiting_seconds": 215.36100006103516, "walking_seconds": 0.0}`.

| Mode | Strict decision | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / lexington_direct | walk_f | 30.67 / 37.61 | 28.29 / 41.96 | -13.67 |
| time_profile | STAY / lexington_direct | walk_f | 30.70 / 37.96 | 28.29 / 39.04 | -10.75 |
| incident_profile | STAY / lexington_direct | walk_f | 30.83 / 37.96 | 28.29 / 39.04 | -10.75 |

The baseline and reassessment select different MTA trains: `MTA:numbered:20261028:5:091550_5..S03R:` becomes `MTA:numbered:20261028:5:099550_5..S03R:`. The duration increase therefore includes a changed catchable train/headway; it is not the same vehicle becoming that many minutes late, and the contemporaneous official delay does not establish that it caused the full increase.

Official as-of notice: Wakefield-241 St-bound [2] and Eastchester-Dyre Av-bound [5] trains are delayed. Downtown [2][5] trains are running with delays. What's Happening? We're performing urgent track maintenance near 3 Av/149 St. Additional service changes: Some uptown [2] trains are rerouted via the [1] line from 96 St to 137 St-City College or 145 St, where they will end. Some uptown [2] trains are rerouted via the [3] line from 135 St to Harlem-148 St, where they will end. Some uptown [2] trains will end at 34 St-Penn Station. Some uptown [5] trains will end at 149 St-Hostos on the [4] line. Listen to announcements to hear how your train will run. Travel Alternatives: For service in the Bronx, consider [4][6][B][D] trains or nearby Bx15 and Bx19 buses.

Exact incident-profile proxy train evidence:

- `lexington_direct` / `MTA:numbered:20261028:5:099550_5..S03R:`: platform-ready 2026-10-28T16:52:55.639000-04:00, inferred departure 2026-10-28T16:54:52-04:00, inferred station arrival 2026-10-28T17:16:13-04:00.
- `walk_f` / `MTA:bdfm:20261028:F:098200_F..S55R:16%3A22%3A01`: platform-ready 2026-10-28T16:59:55.639000-04:00, inferred departure 2026-10-28T17:00:18-04:00, inferred station arrival 2026-10-28T17:20:58-04:00.

Original winner remains fastest in 18/18 single-walk perturbations; this tests +/-two minutes of an access, transfer, or egress component. Exact trips and outcome quality remain in the linked JSON.

### 2026-10-29T16:20:02.813000-04:00

Incident lmm:alert:274022. Anchor 2026-10-29T15:40:53-04:00. First recorded problem boundary 2026-10-29T15:45:53-04:00; first problem receipt 2026-10-29T15:45:55.647000-04:00. Planning interval 39.16 minutes. Initial winner lead 13.95 minutes.

| Route | Before-problem MTA duration, min |
|---|---:|
| lexington_direct | 27.05 |
| broadway_via_7 | 41.00 |
| walk_broadway | 41.00 |
| walk_f | 41.68 |

Stay's unmodified remaining duration deteriorated by 5.60 minutes. Components (seconds): `{"riding_seconds": 90.0, "waiting_seconds": 246.18700003623962, "walking_seconds": 0.0}`.

| Mode | Strict decision | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---:|
| mta | STAY / lexington_direct | walk_f | 32.65 / 39.22 | 28.52 / 40.87 | -12.35 |
| time_profile | STAY / lexington_direct | broadway_via_7 | 33.10 / 39.23 | 28.52 / 38.29 | -9.77 |
| incident_profile | STAY / lexington_direct | broadway_via_7 | 32.34 / 39.29 | 28.52 / 38.29 | -9.77 |

The baseline and reassessment select different MTA trains: `MTA:numbered:20261029:4:090800_4..S06R:` becomes `MTA:numbered:20261029:5:093350_5..S03R:`. The duration increase therefore includes a changed catchable train/headway; it is not the same vehicle becoming that many minutes late, and the contemporaneous official delay does not establish that it caused the full increase.

Official as-of notice: [2][5] trains are running with delays in both directions after we requested EMS assistance for someone in need at Jackson Av. Wakefield-241 St-bound [2] and Eastchester-Dyre Av-bound [5] trains have resumed making local stops from 3 Av/149 St to E 180 St.

Exact incident-profile proxy train evidence:

- `lexington_direct` / `MTA:numbered:20261029:5:093350_5..S03R:`: platform-ready 2026-10-29T16:23:02.813000-04:00, inferred departure 2026-10-29T16:27:48-04:00, inferred station arrival 2026-10-29T16:46:34-04:00.
- `broadway_via_7` / `MTA:numbered:20261029:7:095450_7..S:`: platform-ready 2026-10-29T16:25:02.813000-04:00, inferred departure 2026-10-29T16:25:57-04:00, inferred station arrival 2026-10-29T16:27:54-04:00.
- `broadway_via_7` / `MTA:numbered:20261029:3:097650_3..S06R:`: platform-ready 2026-10-29T16:33:54-04:00, inferred departure 2026-10-29T16:35:56-04:00, inferred station arrival 2026-10-29T16:55:20-04:00.

Original winner remains fastest in 18/18 single-walk perturbations; this tests +/-two minutes of an access, transfer, or egress component. Exact trips and outcome quality remain in the linked JSON.

## Limits

Missing or missed-train outcomes remain unknown. The small correlated sample does not establish a general success rate. These results show one observable later-departure switching opportunity the incident-profile algorithm missed, not proof that the original train became delayed or that this model reliably selects better switches. No model fitting, threshold changes or outcome-driven case replacement occurred.

Full frozen cases: `algo/local/october-preincident-brooklyn/scored-cases.json.gz` (SHA256 `b7d4aa20bea081e6e5b54da79a92f9bd076f1ee0fa832245d6e45b957e911cd4`).
