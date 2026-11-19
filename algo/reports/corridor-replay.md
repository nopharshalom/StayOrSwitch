# Historical corridor replay

The replay screened 140 discovered cutoffs and found 86 qualifying delayed moments involving 24 distinct baseline trains. These correlated moments are not independent incidents. 6 distinct baseline-train examples, spaced at least one hour apart, were selected chronologically before model scoring. The passed segment model's conditional timing actions were {'STAY': 72, 'UNDETERMINED': 14}; its conditional Switch outcomes were 0 faster, 0 not faster, and 0 unknown. Departure-plus-segment research actions were {'SWITCH': 18, 'STAY': 54, 'UNDETERMINED': 14}.

This is an exploratory diagnostic on already-inspected November 12–15, 2026 data. It does not retrain or activate any model, and it is not an unbiased success-rate estimate or a new untouched test.

The Stay route is the fastest **uncorrected MTA** estimate at the same decision time among the two supplied paths. Every mode then selects its train using only that cutoff's available predictions. The MTA mode therefore stays by construction when both paths are assessable.

Outcomes are quality-screened final-prediction proxies, not observed passenger journeys or verified physical train arrivals. Outcome scoring follows exactly the train chosen by each forecast and verifies its inferred departure against platform readiness; a missed train is unknown, with no hindsight replacement.

## Supplied paths and walking assumptions

| Path | Access to platform | Exit to destination |
|---|---:|---:|
| F: Court Sq-23 St to Jay St-MetroTech | 5.0 min | 5.0 min |
| G: Court Sq to Hoyt-Schermerhorn Sts | 4.0 min | 12.0 min |

Two fixed direct subway paths supplied for this experiment; historical trip stop order must confirm each candidate. This is not an exhaustive route search.

Author-selected rounded access-to-platform and exit-to-destination assumptions. Current provider routes were consulted only to sanity-check these values; no historical walking or provider-candidate availability is asserted.

## Case selection and result counts

The source pool contains 140 moments selected without checking model Switch success. 86 have a baseline-fastest train whose inferred outcome is at least 5.0 minutes later than its as-of prediction. Missing or uncatchable baseline outcomes cannot qualify. All pool cases remain in the JSON artifact.

| Mode | Strict actions | Conditional timing actions | Switch outcome: faster / not faster / unknown |
|---|---|---|---|
| Unmodified MTA | {'UNDETERMINED': 46, 'STAY': 40} | {'STAY': 72, 'UNDETERMINED': 14} | 0 / 0 / 0 |
| Passed segment model only | {'UNDETERMINED': 46, 'STAY': 40} | {'STAY': 72, 'UNDETERMINED': 14} | 0 / 0 / 0 |
| Departure + segment (research only) | {'UNDETERMINED': 46, 'STAY': 30, 'SWITCH': 10} | {'SWITCH': 18, 'STAY': 54, 'UNDETERMINED': 14} | 7 / 3 / 8 |

Strict eligibility retains the existing fresh-alert requirement. Archived alerts are content-deduplicated; an old capture does not establish fresh receipt. A conditional timing Switch assumes no unobserved service constraints and is not a recommendation the current app is entitled to emit. Fresh known NO_SERVICE conflicts are still rejected.

The research mode's strict-eligible Switches break down into 0 faster, 3 not faster, and 7 unknown outcomes. Do not combine the number of strict Switches with the conditional-only positive outcomes as a success rate.

The segment model passed its component gate provisionally. Departure failed that gate, so the departure-plus-segment column is research only. Arrival residuals are never added to these routes. Supported disjoint trained segments are corrected at the original cutoff; unsupported or beyond-30-minute segments retain MTA timing, and intermediate dwells are retained once.

Missed timing opportunities among assessable same-selected-train outcomes: the passed segment model stayed despite a faster inferred alternative in 27 qualifying moments; the research mode did so in 18.

| Day type | Discovered cutoffs | Qualifying moments | Segment timing actions | Research timing actions |
|---|---:|---:|---|---|
| WEEKDAY | 117 | 63 | {'STAY': 57, 'UNDETERMINED': 6} | {'SWITCH': 18, 'STAY': 39, 'UNDETERMINED': 6} |
| SATURDAY | 3 | 3 | {'UNDETERMINED': 3} | {'UNDETERMINED': 3} |
| SUNDAY | 20 | 20 | {'UNDETERMINED': 5, 'STAY': 15} | {'UNDETERMINED': 5, 'STAY': 15} |

The chronological detailed examples cover WEEKDAY only; they do not establish weekend behavior. The day-type counts above retain the full discovered pool.

## All qualifying moments

| New York time | Original route | Original ETA duration | Inferred original duration | Original error | Segment action | Research action | Continuity review |
|---|---|---:|---:|---:|---|---|---|
| 11-12 Thu 07:22:05 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.2 | 50.2 | 9.0 | STAY | SWITCH | not flagged |
| 11-12 Thu 07:23:05 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.2 | 49.2 | 9.0 | STAY | STAY | not flagged |
| 11-12 Thu 07:25:05 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.2 | 47.2 | 9.0 | STAY | STAY | not flagged |
| 11-12 Thu 07:26:05 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.2 | 46.2 | 9.0 | STAY | STAY | not flagged |
| 11-12 Thu 07:50:07 | F: Court Sq-23 St to Jay St-MetroTech | 41.1 | 47.4 | 6.3 | STAY | STAY | not flagged |
| 11-12 Thu 07:51:07 | F: Court Sq-23 St to Jay St-MetroTech | 39.5 | 46.4 | 6.9 | STAY | STAY | not flagged |
| 11-12 Thu 07:52:07 | F: Court Sq-23 St to Jay St-MetroTech | 38.5 | 45.4 | 6.9 | STAY | SWITCH | not flagged |
| 11-12 Thu 07:53:07 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.6 | 49.7 | 11.0 | STAY | STAY | not flagged |
| 11-12 Thu 07:54:07 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.6 | 48.7 | 11.0 | STAY | STAY | not flagged |
| 11-12 Thu 07:55:07 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.7 | 49.6 | 11.9 | STAY | STAY | not flagged |
| 11-12 Thu 07:56:07 | G: Court Sq to Hoyt-Schermerhorn Sts | 36.7 | 48.6 | 11.9 | STAY | STAY | not flagged |
| 11-12 Thu 07:57:07 | G: Court Sq to Hoyt-Schermerhorn Sts | 35.7 | 47.6 | 11.9 | STAY | STAY | not flagged |
| 11-12 Thu 07:58:07 | G: Court Sq to Hoyt-Schermerhorn Sts | 34.7 | 46.6 | 11.9 | STAY | STAY | not flagged |
| 11-12 Thu 08:00:07 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.6 | 49.2 | 9.5 | STAY | STAY | not flagged |
| 11-12 Thu 09:02:10 | F: Court Sq-23 St to Jay St-MetroTech | 40.5 | 56.9 | 16.4 | STAY | STAY | not flagged |
| 11-12 Thu 09:14:10 | F: Court Sq-23 St to Jay St-MetroTech | 39.2 | 47.8 | 8.6 | STAY | STAY | not flagged |
| 11-12 Thu 09:15:10 | F: Court Sq-23 St to Jay St-MetroTech | 38.2 | 46.8 | 8.6 | STAY | STAY | not flagged |
| 11-12 Thu 09:21:10 | F: Court Sq-23 St to Jay St-MetroTech | 41.3 | 46.4 | 5.1 | STAY | STAY | not flagged |
| 11-12 Thu 09:21:12 | F: Court Sq-23 St to Jay St-MetroTech | 41.2 | 46.3 | 5.1 | STAY | STAY | not flagged |
| 11-12 Thu 09:23:10 | F: Court Sq-23 St to Jay St-MetroTech | 39.2 | 44.4 | 5.1 | STAY | STAY | not flagged |
| 11-12 Thu 09:23:12 | F: Court Sq-23 St to Jay St-MetroTech | 39.2 | 44.3 | 5.1 | STAY | STAY | not flagged |
| 11-12 Thu 09:24:10 | F: Court Sq-23 St to Jay St-MetroTech | 38.2 | 43.4 | 5.1 | STAY | SWITCH | not flagged |
| 11-12 Thu 09:24:12 | F: Court Sq-23 St to Jay St-MetroTech | 38.2 | 43.3 | 5.1 | STAY | SWITCH | not flagged |
| 11-12 Thu 09:25:12 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.8 | 44.2 | 6.4 | STAY | STAY | not flagged |
| 11-12 Thu 09:26:12 | G: Court Sq to Hoyt-Schermerhorn Sts | 36.8 | 43.2 | 6.4 | STAY | STAY | not flagged |
| 11-12 Thu 12:30:05 | F: Court Sq-23 St to Jay St-MetroTech | 43.4 | 80.0 | 36.7 | STAY | STAY | required |
| 11-12 Thu 12:31:05 | F: Court Sq-23 St to Jay St-MetroTech | 42.4 | 79.0 | 36.7 | STAY | STAY | required |
| 11-12 Thu 12:32:05 | F: Court Sq-23 St to Jay St-MetroTech | 41.4 | 78.0 | 36.7 | STAY | STAY | required |
| 11-12 Thu 12:33:05 | F: Court Sq-23 St to Jay St-MetroTech | 40.4 | 77.0 | 36.7 | STAY | SWITCH | required |
| 11-12 Thu 12:34:05 | F: Court Sq-23 St to Jay St-MetroTech | 39.7 | 76.0 | 36.4 | STAY | SWITCH | required |
| 11-12 Thu 15:06:00 | F: Court Sq-23 St to Jay St-MetroTech | 45.1 | 52.2 | 7.1 | STAY | SWITCH | not flagged |
| 11-12 Thu 15:07:00 | F: Court Sq-23 St to Jay St-MetroTech | 43.9 | 51.2 | 7.3 | STAY | STAY | not flagged |
| 11-12 Thu 15:08:00 | F: Court Sq-23 St to Jay St-MetroTech | 42.9 | 50.2 | 7.3 | STAY | STAY | not flagged |
| 11-12 Thu 15:09:00 | F: Court Sq-23 St to Jay St-MetroTech | 41.9 | 49.2 | 7.3 | STAY | STAY | not flagged |
| 11-12 Thu 15:10:00 | F: Court Sq-23 St to Jay St-MetroTech | 40.9 | 48.2 | 7.3 | STAY | STAY | not flagged |
| 11-12 Thu 15:11:00 | F: Court Sq-23 St to Jay St-MetroTech | 39.9 | 47.2 | 7.3 | STAY | STAY | not flagged |
| 11-12 Thu 15:56:00 | F: Court Sq-23 St to Jay St-MetroTech | 41.1 | 50.9 | 9.7 | STAY | STAY | not flagged |
| 11-12 Thu 15:57:00 | F: Court Sq-23 St to Jay St-MetroTech | 40.6 | 49.9 | 9.3 | STAY | STAY | not flagged |
| 11-12 Thu 15:58:00 | F: Court Sq-23 St to Jay St-MetroTech | 40.6 | 48.9 | 8.3 | STAY | SWITCH | not flagged |
| 11-12 Thu 15:59:00 | F: Court Sq-23 St to Jay St-MetroTech | 38.9 | 47.9 | 8.9 | STAY | SWITCH | not flagged |
| 11-12 Thu 20:28:02 | F: Court Sq-23 St to Jay St-MetroTech | 42.2 | 49.0 | 6.8 | STAY | SWITCH | not flagged |
| 11-12 Thu 20:29:02 | F: Court Sq-23 St to Jay St-MetroTech | 41.2 | 48.0 | 6.8 | STAY | SWITCH | not flagged |
| 11-13 Fri 09:35:07 | F: Court Sq-23 St to Jay St-MetroTech | 38.3 | 44.1 | 5.8 | STAY | STAY | not flagged |
| 11-13 Fri 09:36:07 | F: Court Sq-23 St to Jay St-MetroTech | 37.3 | 43.1 | 5.8 | STAY | STAY | not flagged |
| 11-13 Fri 17:14:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.7 | 102.6 | 62.9 | STAY | SWITCH | required |
| 11-13 Fri 17:15:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.7 | 101.6 | 62.9 | STAY | SWITCH | required |
| 11-13 Fri 17:16:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.7 | 100.6 | 62.9 | STAY | SWITCH | required |
| 11-13 Fri 17:21:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.2 | 179.1 | 137.9 | STAY | SWITCH | required |
| 11-13 Fri 17:22:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.2 | 178.1 | 137.9 | STAY | SWITCH | required |
| 11-13 Fri 17:23:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.2 | 177.1 | 137.9 | STAY | STAY | required |
| 11-13 Fri 17:24:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.2 | 176.1 | 137.9 | STAY | STAY | required |
| 11-13 Fri 17:25:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.2 | 175.1 | 137.9 | STAY | STAY | required |
| 11-13 Fri 20:07:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.5 | 57.6 | 16.1 | STAY | SWITCH | not flagged |
| 11-13 Fri 20:08:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.5 | 56.6 | 16.1 | STAY | SWITCH | not flagged |
| 11-13 Fri 20:09:03 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.4 | 55.6 | 16.1 | STAY | STAY | not flagged |
| 11-13 Fri 20:10:03 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.4 | 54.6 | 16.1 | STAY | STAY | not flagged |
| 11-13 Fri 20:11:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.5 | 53.6 | 16.1 | STAY | STAY | not flagged |
| 11-13 Fri 22:18:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.2 | 46.4 | 5.2 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-13 Fri 22:19:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.2 | 45.4 | 5.2 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-13 Fri 22:20:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.2 | 44.4 | 5.2 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-13 Fri 22:21:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.2 | 43.4 | 5.2 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-13 Fri 22:22:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.2 | 42.4 | 5.2 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-13 Fri 22:23:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 36.2 | 41.4 | 5.2 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-14 Sat 13:14:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 42.0 | 47.4 | 5.5 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-14 Sat 13:15:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.0 | 46.4 | 5.5 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-14 Sat 13:16:02 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.0 | 45.4 | 5.5 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-15 Sun 14:37:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.5 | 47.1 | 5.6 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-15 Sun 14:38:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.5 | 46.1 | 5.6 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-15 Sun 14:39:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.5 | 45.1 | 5.6 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-15 Sun 14:40:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.5 | 44.1 | 5.6 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-15 Sun 14:41:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.5 | 43.1 | 5.6 | UNDETERMINED | UNDETERMINED | not flagged |
| 11-15 Sun 18:53:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.5 | 48.9 | 7.5 | STAY | STAY | not flagged |
| 11-15 Sun 18:54:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.5 | 47.9 | 7.5 | STAY | STAY | not flagged |
| 11-15 Sun 18:55:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.5 | 46.9 | 7.5 | STAY | STAY | not flagged |
| 11-15 Sun 18:56:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.5 | 45.9 | 7.5 | STAY | STAY | not flagged |
| 11-15 Sun 18:57:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.5 | 44.9 | 7.5 | STAY | STAY | not flagged |
| 11-15 Sun 19:01:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.5 | 60.1 | 18.6 | STAY | STAY | not flagged |
| 11-15 Sun 19:02:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.5 | 59.1 | 18.6 | STAY | STAY | not flagged |
| 11-15 Sun 19:03:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.5 | 58.1 | 18.6 | STAY | STAY | not flagged |
| 11-15 Sun 19:04:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.5 | 57.1 | 18.6 | STAY | STAY | not flagged |
| 11-15 Sun 19:05:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.5 | 56.1 | 18.6 | STAY | STAY | not flagged |
| 11-15 Sun 19:17:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 41.5 | 47.7 | 6.2 | STAY | STAY | not flagged |
| 11-15 Sun 19:18:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 40.5 | 46.7 | 6.2 | STAY | STAY | not flagged |
| 11-15 Sun 19:19:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 39.5 | 45.7 | 6.2 | STAY | STAY | not flagged |
| 11-15 Sun 19:20:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 38.5 | 44.7 | 6.2 | STAY | STAY | not flagged |
| 11-15 Sun 19:21:00 | G: Court Sq to Hoyt-Schermerhorn Sts | 37.5 | 43.7 | 6.2 | STAY | STAY | not flagged |

All durations below are door-to-door minutes. Positive Switch outcome savings means the alternative's forecast-selected train arrived earlier than the same mode's selected train on the Stay route. Strategy gain compares the recommendation against the original uncorrected MTA train instead; these are separate quantities.

## Detailed cases

Detailed cases are the earliest qualifying distinct source-pool moments in chronological order, up to the declared limit. They are not chosen for a favorable recommendation.

### 2026-11-12-G-072205 — 11-12 Thu 07:22:05

Original route: **G: Court Sq to Hoyt-Schermerhorn Sts**. As-of duration 41.2 min; inferred duration 50.2 min; forecast error +9.0 min.

| Mode and path | Predicted duration | Inferred selected-train duration | Model coverage |
|---|---:|---:|---|
| Unmodified MTA: F: Court Sq-23 St to Jay St-MetroTech | 41.3 | UNAVAILABLE | segments 0 applied / 0 fallback; departure unchanged |
| Unmodified MTA: G: Court Sq to Hoyt-Schermerhorn Sts | 41.2 | 50.2 | segments 0 applied / 0 fallback; departure unchanged |
| Passed segment model only: F: Court Sq-23 St to Jay St-MetroTech | 41.4 | UNAVAILABLE | segments 2 applied / 1 fallback; departure unchanged |
| Passed segment model only: G: Court Sq to Hoyt-Schermerhorn Sts | 41.4 | 50.2 | segments 3 applied / 0 fallback; departure unchanged |
| Departure + segment (research only): F: Court Sq-23 St to Jay St-MetroTech | 37.5 | 38.0 | segments 2 applied / 1 fallback; departure applied |
| Departure + segment (research only): G: Court Sq to Hoyt-Schermerhorn Sts | 41.7 | 50.2 | segments 3 applied / 0 fallback; departure applied |

| Mode | Strict decision | Conditional timing decision | Predicted Switch savings | Inferred Switch savings | Strategy gain vs original MTA train |
|---|---|---|---:|---:|---:|
| Unmodified MTA | UNDETERMINED | STAY | 0.0 | 0.0 | 0.0 |
| Passed segment model only | UNDETERMINED | STAY | 0.0 | 0.0 | 0.0 |
| Departure + segment (research only) | UNDETERMINED | SWITCH | 4.2 | 12.1 | 12.1 |

Walking sensitivity: 81 independent access/egress scenarios, each varied by −2, 0, or +2 minutes. Trains and the original route are reselected in each scenario. Reference counts: {'f_court_sq_jay': 45, 'g_court_sq_hoyt': 36}. Segment actions: {'STAY': 81}; research actions: {'STAY': 63, 'SWITCH': 18}.

### 2026-11-12-F-090210 — 11-12 Thu 09:02:10

Original route: **F: Court Sq-23 St to Jay St-MetroTech**. As-of duration 40.5 min; inferred duration 56.9 min; forecast error +16.4 min.

| Mode and path | Predicted duration | Inferred selected-train duration | Model coverage |
|---|---:|---:|---|
| Unmodified MTA: F: Court Sq-23 St to Jay St-MetroTech | 40.5 | 56.9 | segments 0 applied / 0 fallback; departure unchanged |
| Unmodified MTA: G: Court Sq to Hoyt-Schermerhorn Sts | 44.6 | UNAVAILABLE | segments 0 applied / 0 fallback; departure unchanged |
| Passed segment model only: F: Court Sq-23 St to Jay St-MetroTech | 40.6 | 56.9 | segments 2 applied / 1 fallback; departure unchanged |
| Passed segment model only: G: Court Sq to Hoyt-Schermerhorn Sts | 45.2 | UNAVAILABLE | segments 1 applied / 2 fallback; departure unchanged |
| Departure + segment (research only): F: Court Sq-23 St to Jay St-MetroTech | 37.4 | MISSED_SELECTED_TRAIN | segments 2 applied / 1 fallback; departure applied |
| Departure + segment (research only): G: Court Sq to Hoyt-Schermerhorn Sts | 45.5 | UNAVAILABLE | segments 1 applied / 2 fallback; departure applied |

| Mode | Strict decision | Conditional timing decision | Predicted Switch savings | Inferred Switch savings | Strategy gain vs original MTA train |
|---|---|---|---:|---:|---:|
| Unmodified MTA | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Passed segment model only | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Departure + segment (research only) | STAY | STAY | 0.0 | unknown | unknown |

Walking sensitivity: 81 independent access/egress scenarios, each varied by −2, 0, or +2 minutes. Trains and the original route are reselected in each scenario. Reference counts: {'f_court_sq_jay': 60, 'g_court_sq_hoyt': 21}. Segment actions: {'STAY': 81}; research actions: {'SWITCH': 8, 'STAY': 73}.

### 2026-11-12-F-123005 — 11-12 Thu 12:30:05

Original route: **F: Court Sq-23 St to Jay St-MetroTech**. As-of duration 43.4 min; inferred duration 80.0 min; forecast error +36.7 min.

This discovery event has an unresolved long-trip continuity warning. Screened endpoint labels do not independently establish that the entire unusual delay is physical; interpret its proxy savings conditionally.

| Mode and path | Predicted duration | Inferred selected-train duration | Model coverage |
|---|---:|---:|---|
| Unmodified MTA: F: Court Sq-23 St to Jay St-MetroTech | 43.4 | 80.0 | segments 0 applied / 0 fallback; departure unchanged |
| Unmodified MTA: G: Court Sq to Hoyt-Schermerhorn Sts | 44.7 | 45.0 | segments 0 applied / 0 fallback; departure unchanged |
| Passed segment model only: F: Court Sq-23 St to Jay St-MetroTech | 43.4 | 80.0 | segments 2 applied / 1 fallback; departure unchanged |
| Passed segment model only: G: Court Sq to Hoyt-Schermerhorn Sts | 45.6 | 45.0 | segments 2 applied / 1 fallback; departure unchanged |
| Departure + segment (research only): F: Court Sq-23 St to Jay St-MetroTech | 45.6 | 80.0 | segments 2 applied / 1 fallback; departure applied |
| Departure + segment (research only): G: Court Sq to Hoyt-Schermerhorn Sts | 45.8 | 45.0 | segments 2 applied / 1 fallback; departure applied |

| Mode | Strict decision | Conditional timing decision | Predicted Switch savings | Inferred Switch savings | Strategy gain vs original MTA train |
|---|---|---|---:|---:|---:|
| Unmodified MTA | UNDETERMINED | STAY | 0.0 | 0.0 | 0.0 |
| Passed segment model only | UNDETERMINED | STAY | 0.0 | 0.0 | 0.0 |
| Departure + segment (research only) | UNDETERMINED | STAY | 0.0 | 0.0 | 0.0 |

Walking sensitivity: 81 independent access/egress scenarios, each varied by −2, 0, or +2 minutes. Trains and the original route are reselected in each scenario. Reference counts: {'g_court_sq_hoyt': 36, 'f_court_sq_jay': 45}. Segment actions: {'SWITCH': 11, 'STAY': 70}; research actions: {'STAY': 81}.

### 2026-11-12-F-150600 — 11-12 Thu 15:06:00

Original route: **F: Court Sq-23 St to Jay St-MetroTech**. As-of duration 45.1 min; inferred duration 52.2 min; forecast error +7.1 min.

| Mode and path | Predicted duration | Inferred selected-train duration | Model coverage |
|---|---:|---:|---|
| Unmodified MTA: F: Court Sq-23 St to Jay St-MetroTech | 45.1 | 52.2 | segments 0 applied / 0 fallback; departure unchanged |
| Unmodified MTA: G: Court Sq to Hoyt-Schermerhorn Sts | 46.7 | 46.6 | segments 0 applied / 0 fallback; departure unchanged |
| Passed segment model only: F: Court Sq-23 St to Jay St-MetroTech | 45.1 | 52.2 | segments 2 applied / 1 fallback; departure unchanged |
| Passed segment model only: G: Court Sq to Hoyt-Schermerhorn Sts | 47.4 | 46.6 | segments 1 applied / 2 fallback; departure unchanged |
| Departure + segment (research only): F: Court Sq-23 St to Jay St-MetroTech | 47.3 | 52.2 | segments 2 applied / 1 fallback; departure applied |
| Departure + segment (research only): G: Court Sq to Hoyt-Schermerhorn Sts | 37.2 | MISSED_SELECTED_TRAIN | segments 3 applied / 0 fallback; departure applied |

| Mode | Strict decision | Conditional timing decision | Predicted Switch savings | Inferred Switch savings | Strategy gain vs original MTA train |
|---|---|---|---:|---:|---:|
| Unmodified MTA | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Passed segment model only | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Departure + segment (research only) | SWITCH | SWITCH | 10.1 | unknown | unknown |

Walking sensitivity: 81 independent access/egress scenarios, each varied by −2, 0, or +2 minutes. Trains and the original route are reselected in each scenario. Reference counts: {'g_court_sq_hoyt': 45, 'f_court_sq_jay': 36}. Segment actions: {'STAY': 69, 'SWITCH': 12}; research actions: {'STAY': 60, 'SWITCH': 21}.

### 2026-11-12-F-202802 — 11-12 Thu 20:28:02

Original route: **F: Court Sq-23 St to Jay St-MetroTech**. As-of duration 42.2 min; inferred duration 49.0 min; forecast error +6.8 min.

| Mode and path | Predicted duration | Inferred selected-train duration | Model coverage |
|---|---:|---:|---|
| Unmodified MTA: F: Court Sq-23 St to Jay St-MetroTech | 42.2 | 49.0 | segments 0 applied / 0 fallback; departure unchanged |
| Unmodified MTA: G: Court Sq to Hoyt-Schermerhorn Sts | 43.2 | UNAVAILABLE | segments 0 applied / 0 fallback; departure unchanged |
| Passed segment model only: F: Court Sq-23 St to Jay St-MetroTech | 42.4 | 49.0 | segments 2 applied / 1 fallback; departure unchanged |
| Passed segment model only: G: Court Sq to Hoyt-Schermerhorn Sts | 44.0 | UNAVAILABLE | segments 2 applied / 1 fallback; departure unchanged |
| Departure + segment (research only): F: Court Sq-23 St to Jay St-MetroTech | 44.3 | 49.0 | segments 2 applied / 1 fallback; departure applied |
| Departure + segment (research only): G: Court Sq to Hoyt-Schermerhorn Sts | 44.0 | UNAVAILABLE | segments 2 applied / 1 fallback; departure applied |

| Mode | Strict decision | Conditional timing decision | Predicted Switch savings | Inferred Switch savings | Strategy gain vs original MTA train |
|---|---|---|---:|---:|---:|
| Unmodified MTA | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Passed segment model only | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Departure + segment (research only) | SWITCH | SWITCH | 0.3 | unknown | unknown |

Walking sensitivity: 81 independent access/egress scenarios, each varied by −2, 0, or +2 minutes. Trains and the original route are reselected in each scenario. Reference counts: {'g_court_sq_hoyt': 45, 'f_court_sq_jay': 36}. Segment actions: {'STAY': 81}; research actions: {'STAY': 63, 'SWITCH': 18}.

### 2026-11-13-F-093507 — 11-13 Fri 09:35:07

Original route: **F: Court Sq-23 St to Jay St-MetroTech**. As-of duration 38.3 min; inferred duration 44.1 min; forecast error +5.8 min.

| Mode and path | Predicted duration | Inferred selected-train duration | Model coverage |
|---|---:|---:|---|
| Unmodified MTA: F: Court Sq-23 St to Jay St-MetroTech | 38.3 | 44.1 | segments 0 applied / 0 fallback; departure unchanged |
| Unmodified MTA: G: Court Sq to Hoyt-Schermerhorn Sts | 42.6 | 44.2 | segments 0 applied / 0 fallback; departure unchanged |
| Passed segment model only: F: Court Sq-23 St to Jay St-MetroTech | 38.4 | 44.1 | segments 2 applied / 1 fallback; departure unchanged |
| Passed segment model only: G: Court Sq to Hoyt-Schermerhorn Sts | 43.4 | 44.2 | segments 2 applied / 1 fallback; departure unchanged |
| Departure + segment (research only): F: Court Sq-23 St to Jay St-MetroTech | 40.4 | 44.1 | segments 2 applied / 1 fallback; departure applied |
| Departure + segment (research only): G: Court Sq to Hoyt-Schermerhorn Sts | 43.5 | 44.2 | segments 2 applied / 1 fallback; departure applied |

| Mode | Strict decision | Conditional timing decision | Predicted Switch savings | Inferred Switch savings | Strategy gain vs original MTA train |
|---|---|---|---:|---:|---:|
| Unmodified MTA | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Passed segment model only | STAY | STAY | 0.0 | 0.0 | 0.0 |
| Departure + segment (research only) | STAY | STAY | 0.0 | 0.0 | 0.0 |

Walking sensitivity: 81 independent access/egress scenarios, each varied by −2, 0, or +2 minutes. Trains and the original route are reselected in each scenario. Reference counts: {'g_court_sq_hoyt': 31, 'f_court_sq_jay': 50}. Segment actions: {'STAY': 81}; research actions: {'STAY': 72, 'SWITCH': 9}.

## Reproduction and limits

Frozen experiment seal: `eb30157cd1b07f25fe2c197adbfaf34220baf988b73d9edb9d6613a03c7a70e6`. Dependencies were verified before and after replay; the seal is unchanged. No arrival/departure adoption decision has changed.

The JSON artifact contains every supplied path, chosen service-qualified train identity, model application/fallback, forecast/outcome timing, alert freshness, rejected candidates, unknown outcomes, and walking-sensitivity scenario. Only the supplied direct F and G paths are compared; transfers, other lines, street disruptions, entrance access, physical walking observations, and routes absent from the as-of train horizon are outside this diagnostic.

Source bundle: `data/processed/corridor-replay/replay-bundle.json.gz`. Configuration: `/Users/hollisyang/Desktop/Studio/StayOrSwitch/data/config/corridor-replay.json`.
