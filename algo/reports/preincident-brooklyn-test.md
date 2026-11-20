# Pre-incident fastest-route delay replay

This is an exploratory, post-hoc search within October 25–31. The original predictor and development profiles are unchanged. The new Stay route is selected before the first problem, using only then-available feeds. It is fastest among the supplied alternatives, not a historical Google route or an exhaustive citywide optimum.

Origin: Grand Central street entrance at East 42nd Street and Lexington Avenue. Destination: Brooklyn Borough Hall street corner at Court Street and Joralemon Street. Both comparisons start anew from the same origin; the person has not boarded. The interval between planning and reassessment is not added to the new journey duration.

Authored walking per candidate (seconds): `{"broadway_via_7": {"access_walk_seconds": 300, "egress_walk_seconds": 180, "transfer_walk_seconds": [360]}, "lexington_direct": {"access_walk_seconds": 180, "egress_walk_seconds": 120, "transfer_walk_seconds": []}, "walk_broadway": {"access_walk_seconds": 960, "egress_walk_seconds": 180, "transfer_walk_seconds": []}, "walk_f": {"access_walk_seconds": 600, "egress_walk_seconds": 480, "transfer_walk_seconds": []}}`. These are research assumptions, including station access; all one-component +/-120-second sensitivities are retained, including whether the original fastest route remains fastest.

An anchor must precede the earlier of the first incident receipt and its initially declared active start, and its fastest route must have fresh NORMAL evidence. All supplied alternatives need complete timing and verified service evidence. Fixed lookbacks are 1/5/10/15/30 minutes. A baseline lead of three minutes or less is flagged as a near tie.

At reassessment the same route must carry an applicable official delay notice and its remaining MTA duration must increase by at least five minutes. Waiting and riding changes are separate. This does not prove causation: headways and train selection also change. Ordinary disruption is sufficient in this request, so the existing comparator uses require_severe=False; its five-minute Switch margin and three-minute outcome tie remain unchanged. A maintenance-related delay whose planning status is unspecified is not asserted to be unplanned.

Confirmed cases: **31**; distinct incident families: **11**.

| Mode | Scope | Switch | Scorable | Unknown | Gains >3 min | Ties | Losses >3 min |
|---|---|---:|---:|---:|---:|---:|---:|
| mta | strict_decision | 4 | 0 | 4 | 0 | 0 | 0 |
| mta | conditional_timing_decision | 7 | 0 | 7 | 0 | 0 | 0 |
| time_profile | strict_decision | 6 | 3 | 3 | 0 | 0 | 3 |
| time_profile | conditional_timing_decision | 9 | 3 | 6 | 0 | 0 | 3 |
| incident_profile | strict_decision | 4 | 1 | 3 | 0 | 0 | 1 |
| incident_profile | conditional_timing_decision | 7 | 1 | 6 | 0 | 0 | 1 |

Forecast-best alternative compared with Stay regardless of the issued decision:

| Mode | Comparable | Gain >3 min | Tie | Loss >3 min | Unknown | Gain missed by strict STAY |
|---|---:|---:|---:|---:|---:|---:|
| mta | 19 | 3 | 1 | 15 | 12 | 2 |
| time_profile | 15 | 3 | 0 | 12 | 16 | 3 |
| incident_profile | 11 | 2 | 0 | 9 | 20 | 2 |

Cases within an incident are correlated. Unknowns and missed selected trains are not successes. Scored arrival times are screened final MTA prediction proxies plus authored walks, not independently observed passenger arrivals.

## Case illustrations

The report retains the first input-qualified case per incident, plus the earliest comparable incident-profile Stay versus forecast-best alternative per incident, regardless of action or winner. The latter are explicitly outcome-selected illustrations and do not define the evaluation population.

### 2026-10-25T02:32:32.704000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:273391.

Pre-problem anchor: 2026-10-25T02:27:31-04:00. Problem boundary: 2026-10-25T02:32:31-04:00. First problem receipt: 2026-10-25T02:32:32.704000-04:00. Winner lead: 16.9 min; near tie: False. Planning interval: 5.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 29.0 | 44.5 |
| broadway_via_7 | 70.6 | 50.2 |
| walk_broadway | 54.4 | 50.2 |
| walk_f | 46.0 | 40.1 |

Stay duration deterioration: 15.4 min; component changes (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 925.2960000038147, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | walk_f | 44.5 / 40.1 | 44.4 / 48.0 | -3.5 |
| time_profile | SWITCH | walk_f | walk_f | 48.6 / 43.0 | 44.4 / 48.0 | -3.5 |
| incident_profile | STAY | lexington_direct | walk_f | 46.7 / 43.0 | 44.4 / 48.0 | -3.5 |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 2/18.

### 2026-10-26T03:16:00.539000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:273480.

Pre-problem anchor: 2026-10-26T03:14:59-04:00. Problem boundary: 2026-10-26T03:15:59-04:00. First problem receipt: 2026-10-26T03:16:00.539000-04:00. Winner lead: 15.9 min; near tie: False. Planning interval: 1.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 29.8 | 47.5 |
| broadway_via_7 | 67.7 | 67.1 |
| walk_broadway | 45.7 | 44.8 |
| walk_f | 47.3 | 46.8 |

Stay duration deterioration: 17.7 min; component changes (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 1063.4609999656677, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | walk_broadway | 47.5 / 44.8 | 52.0 / 47.7 | 4.2 |
| time_profile | STAY | lexington_direct | walk_broadway | 48.7 / 47.1 | 52.0 / 47.7 | 4.2 |
| incident_profile | STAY | lexington_direct | walk_broadway | 33.2 / 46.9 | unknown / 47.7 | unknown |

Walking stress tests: original winner remains fastest in 17/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-26T03:21:00.539000-04:00 — lexington_direct

Selection: OUTCOME_SELECTED_ILLUSTRATION. Incident: lmm:alert:273480.

Pre-problem anchor: 2026-10-26T03:14:59-04:00. Problem boundary: 2026-10-26T03:15:59-04:00. First problem receipt: 2026-10-26T03:16:00.539000-04:00. Winner lead: 15.9 min; near tie: False. Planning interval: 6.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 29.8 | 41.6 |
| broadway_via_7 | 67.7 | 63.4 |
| walk_broadway | 45.7 | 63.4 |
| walk_f | 47.3 | 42.5 |

Stay duration deterioration: 11.8 min; component changes (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 710.4609999656677, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | walk_f | 41.6 / 42.5 | 47.0 / 39.7 | 7.2 |
| time_profile | STAY | lexington_direct | walk_f | 42.8 / 45.4 | 47.0 / 39.7 | 7.2 |
| incident_profile | STAY | lexington_direct | walk_f | 45.7 / 45.4 | 47.0 / 39.7 | 7.2 |

Walking stress tests: original winner remains fastest in 17/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-26T20:39:38.618000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:273610.

Pre-problem anchor: 2026-10-26T20:34:37-04:00. Problem boundary: 2026-10-26T20:39:37-04:00. First problem receipt: 2026-10-26T20:39:38.618000-04:00. Winner lead: 14.0 min; near tie: False. Planning interval: 5.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 24.3 | 33.3 |
| broadway_via_7 | 44.0 | 38.0 |
| walk_broadway | 38.3 | 42.4 |
| walk_f | 43.4 | 38.0 |

Stay duration deterioration: 9.0 min; component changes (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 542.3819999694824, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | broadway_via_7 | 33.3 / 38.0 | 32.3 / unknown | unknown |
| time_profile | STAY | lexington_direct | broadway_via_7 | 32.4 / 38.3 | 32.3 / unknown | unknown |
| incident_profile | STAY | lexington_direct | broadway_via_7 | 32.1 / 38.3 | 32.3 / unknown | unknown |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-27T08:09:03.779000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:273660.

Pre-problem anchor: 2026-10-27T07:59:02-04:00. Problem boundary: 2026-10-27T08:04:02-04:00. First problem receipt: 2026-10-27T08:04:03.779000-04:00. Winner lead: 11.7 min; near tie: False. Planning interval: 10.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 26.9 | 35.0 |
| broadway_via_7 | 38.6 | 41.3 |
| walk_broadway | 38.6 | 41.3 |
| walk_f | 38.8 | 38.4 |

Stay duration deterioration: 8.1 min; component changes (seconds): `{"riding_seconds": 30.0, "waiting_seconds": 454.220999956131, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | walk_f | 35.0 / 38.4 | 34.1 / 41.2 | -7.1 |
| time_profile | STAY | lexington_direct | walk_f | 33.9 / 41.3 | 34.1 / 41.2 | -7.1 |
| incident_profile | STAY | lexington_direct | walk_f | 25.2 / 41.3 | unknown / 41.2 | unknown |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-27T17:23:22.725000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:273712.

Pre-problem anchor: 2026-10-27T16:03:20-04:00. Problem boundary: 2026-10-27T16:33:20-04:00. First problem receipt: 2026-10-27T16:33:22.725000-04:00. Winner lead: 11.1 min; near tie: False. Planning interval: 80.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 27.1 | 35.0 |
| broadway_via_7 | 40.7 | 38.9 |
| walk_broadway | 40.7 | 38.9 |
| walk_f | 38.2 | 40.4 |

Stay duration deterioration: 7.9 min; component changes (seconds): `{"riding_seconds": 90.0, "waiting_seconds": 383.27500009536743, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | UNDETERMINED | none | broadway_via_7 | 35.0 / 38.9 | 60.8 / 39.1 | 21.7 |
| time_profile | UNDETERMINED | none | broadway_via_7 | 26.6 / 38.6 | 30.5 / unknown | unknown |
| incident_profile | UNDETERMINED | none | broadway_via_7 | 30.2 / 38.7 | unknown / unknown | unknown |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-28T09:46:52.722000-04:00 — walk_f

Selection: INPUT_FIRST. Incident: lmm:alert:273822.

Pre-problem anchor: 2026-10-28T08:26:50-04:00. Problem boundary: 2026-10-28T08:56:50-04:00. First problem receipt: 2026-10-28T08:56:52.722000-04:00. Winner lead: 0.3 min; near tie: True. Planning interval: 80.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 38.7 | 28.0 |
| broadway_via_7 | 37.6 | 39.4 |
| walk_broadway | 39.2 | 39.4 |
| walk_f | 37.3 | 48.0 |

Stay duration deterioration: 10.6 min; component changes (seconds): `{"riding_seconds": 105.0, "waiting_seconds": 533.2780001163483, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | UNDETERMINED | none | lexington_direct | 48.0 / 28.0 | unknown / 27.8 | unknown |
| time_profile | UNDETERMINED | none | lexington_direct | 38.3 / 26.8 | unknown / 27.8 | unknown |
| incident_profile | UNDETERMINED | none | lexington_direct | 38.3 / 26.8 | unknown / 27.8 | unknown |

Walking stress tests: original winner remains fastest in 11/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-28T10:36:52.722000-04:00 — walk_f

Selection: OUTCOME_SELECTED_ILLUSTRATION. Incident: lmm:alert:273822.

Pre-problem anchor: 2026-10-28T08:26:50-04:00. Problem boundary: 2026-10-28T08:56:50-04:00. First problem receipt: 2026-10-28T08:56:52.722000-04:00. Winner lead: 0.3 min; near tie: True. Planning interval: 130.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 38.7 | 29.1 |
| broadway_via_7 | 37.6 | 46.8 |
| walk_broadway | 39.2 | 42.6 |
| walk_f | 37.3 | 42.4 |

Stay duration deterioration: 5.1 min; component changes (seconds): `{"riding_seconds": 30.0, "waiting_seconds": 273.27800011634827, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | SWITCH | lexington_direct | lexington_direct | 42.4 / 29.1 | unknown / 46.1 | unknown |
| time_profile | SWITCH | lexington_direct | lexington_direct | 39.8 / 28.6 | 39.0 / 46.1 | -7.1 |
| incident_profile | SWITCH | lexington_direct | lexington_direct | 39.8 / 33.5 | 39.0 / 46.1 | -7.1 |

Walking stress tests: original winner remains fastest in 11/18 variations; formal incident-profile Switch occurs in 16/18.

### 2026-10-28T16:49:55.639000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:273870.

Pre-problem anchor: 2026-10-28T15:58:53-04:00. Problem boundary: 2026-10-28T15:59:53-04:00. First problem receipt: 2026-10-28T15:59:55.639000-04:00. Winner lead: 12.2 min; near tie: False. Planning interval: 51.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 25.6 | 30.7 |
| broadway_via_7 | 37.8 | 41.4 |
| walk_broadway | 42.0 | 41.4 |
| walk_f | 38.7 | 37.6 |

Stay duration deterioration: 5.1 min; component changes (seconds): `{"riding_seconds": 90.0, "waiting_seconds": 215.36100006103516, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | walk_f | 30.7 / 37.6 | 28.3 / 42.0 | -13.7 |
| time_profile | STAY | lexington_direct | walk_f | 30.7 / 38.0 | 28.3 / 39.0 | -10.8 |
| incident_profile | STAY | lexington_direct | walk_f | 30.8 / 38.0 | 28.3 / 39.0 | -10.8 |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-28T19:05:32.748000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:273887.

Pre-problem anchor: 2026-10-28T17:26:40-04:00. Problem boundary: 2026-10-28T17:31:40-04:00. First problem receipt: 2026-10-28T17:31:42.727000-04:00. Winner lead: 11.5 min; near tie: False. Planning interval: 98.9 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 31.6 | 41.0 |
| broadway_via_7 | 44.3 | 36.3 |
| walk_broadway | 44.3 | 40.4 |
| walk_f | 43.1 | 37.5 |

Stay duration deterioration: 9.4 min; component changes (seconds): `{"riding_seconds": -150.0, "waiting_seconds": 713.2520000934601, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | broadway_via_7 | 41.0 / 36.3 | 41.4 / unknown | unknown |
| time_profile | STAY | lexington_direct | broadway_via_7 | 41.1 / 40.4 | 41.4 / unknown | unknown |
| incident_profile | STAY | lexington_direct | broadway_via_7 | 23.8 / 40.4 | unknown / unknown | unknown |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-29T16:20:02.813000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:274022.

Pre-problem anchor: 2026-10-29T15:40:53-04:00. Problem boundary: 2026-10-29T15:45:53-04:00. First problem receipt: 2026-10-29T15:45:55.647000-04:00. Winner lead: 13.9 min; near tie: False. Planning interval: 39.2 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 27.1 | 32.7 |
| broadway_via_7 | 41.0 | 39.6 |
| walk_broadway | 41.0 | 39.6 |
| walk_f | 41.7 | 39.2 |

Stay duration deterioration: 5.6 min; component changes (seconds): `{"riding_seconds": 90.0, "waiting_seconds": 246.18700003623962, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | walk_f | 32.7 / 39.2 | 28.5 / 40.9 | -12.3 |
| time_profile | STAY | lexington_direct | broadway_via_7 | 33.1 / 39.2 | 28.5 / 38.3 | -9.8 |
| incident_profile | STAY | lexington_direct | broadway_via_7 | 32.3 / 39.3 | 28.5 / 38.3 | -9.8 |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-31T13:17:27.714000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:274347.

Pre-problem anchor: 2026-10-31T13:16:25-04:00. Problem boundary: 2026-10-31T13:17:25-04:00. First problem receipt: 2026-10-31T13:17:27.714000-04:00. Winner lead: 14.4 min; near tie: False. Planning interval: 1.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 24.0 | 33.8 |
| broadway_via_7 | 38.4 | 37.5 |
| walk_broadway | 38.4 | 37.5 |
| walk_f | 53.9 | 52.6 |

Stay duration deterioration: 9.9 min; component changes (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 591.2860000133514, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | STAY | lexington_direct | broadway_via_7 | 33.8 / 37.5 | 30.2 / unknown | unknown |
| time_profile | STAY | lexington_direct | broadway_via_7 | 32.7 / 39.1 | 30.2 / unknown | unknown |
| incident_profile | STAY | lexington_direct | broadway_via_7 | 33.8 / 39.3 | 30.2 / unknown | unknown |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

### 2026-10-31T21:45:03.694000-04:00 — lexington_direct

Selection: INPUT_FIRST. Incident: lmm:alert:274395.

Pre-problem anchor: 2026-10-31T20:55:02-04:00. Problem boundary: 2026-10-31T21:05:02-04:00. First problem receipt: 2026-10-31T21:05:03.694000-04:00. Winner lead: 21.1 min; near tie: False. Planning interval: 50.0 min.

| Route | Before-problem MTA min | Delay-time MTA min |
|---|---:|---:|
| lexington_direct | 25.4 | 31.9 |
| broadway_via_7 | 46.8 | 37.9 |
| walk_broadway | 46.8 | 37.9 |
| walk_f | 46.5 | 51.0 |

Stay duration deterioration: 6.5 min; component changes (seconds): `{"riding_seconds": 0.0, "waiting_seconds": 388.30599999427795, "walking_seconds": 0.0}`.

| Mode | Strict action | Strict recommended route | Forecast-best alternative | Predicted Stay / alternative min | Proxy Stay / alternative min | Alternative proxy saving min |
|---|---|---|---|---|---|---:|
| mta | UNDETERMINED | none | broadway_via_7 | 31.9 / 37.9 | 31.1 / unknown | unknown |
| time_profile | UNDETERMINED | none | broadway_via_7 | 31.7 / 41.5 | 31.1 / unknown | unknown |
| incident_profile | UNDETERMINED | none | broadway_via_7 | 35.3 / 37.4 | 31.1 / unknown | unknown |

Walking stress tests: original winner remains fastest in 18/18 variations; formal incident-profile Switch occurs in 0/18.

## Coverage and limitations

The case table compares Stay with the forecast-best alternative even when the algorithm says STAY. This is a counterfactual diagnostic, not a recommendation to switch. JSON separately records the best alternative known from later outcomes and missed-opportunity counts; hindsight never selects a recommendation or the evaluation cohort.

Input selection rejections and every pre-problem anchor attempt are preserved in the prepared artifact and candidate-selection report. Official route/direction qualification is separate from the original classifier; planned work, opposite directions and narrow notices beyond the traversed segment are excluded.

New segments outside the frozen training groups explicitly fall back; existing component segments retain development-only profiles. Supplemental endpoint outcomes, when needed, use unchanged original quality rules. No new regressor is trained.

Full cases: `algo/local/october-preincident-brooklyn/scored-cases.json.gz` (SHA256 `b7d4aa20bea081e6e5b54da79a92f9bd076f1ee0fa832245d6e45b957e911cd4`).
