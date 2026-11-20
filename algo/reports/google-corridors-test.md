# Current Google Stay paths under historical service problems

Google's current recommended path defines Stay; its present-day ETA is context only. Every historical journey departs unboarded at the event's own information cutoff. The current path is not claimed to have been the fastest path in October.

This post-hoc test uses October 25–31 official service problems and fixed 0/5/10/15/30/60/120-minute checkpoints after the first problem version naming the Stay line, plus the exact receipts of later relevant problem versions inside that two-hour window. All input-selected confirmed encounters are retained. The primary event representative is the earliest confirmed checkpoint with usable Stay timing, or the earliest unknown encounter if none has timing. Selection and text scope were frozen before labels were opened.

Final MTA predictions are screened outcome proxies, not independently observed passenger arrivals. Current-provider and explicitly authored walking times are held fixed; they are not historical pedestrian measurements. Unknown or missed selected trains remain unknown. Historical models and the five-minute Switch margin are unchanged.

Same boarding/alighting station paths with another line, such as 5 to 4, are marked as same-station-path service substitutions rather than geographic detours. Invalid Google candidates remain unavailable, never silently slower.

## pilot_hayden_tandon

Hayden LIC Apartments, 43-25 Hunter Street, Long Island City, NY 11101 → NYU Tandon School of Engineering, 6 MetroTech Center, Brooklyn, NY 11201.

Google-defined Stay: `google-route-f1879a6d65f5e73756e1b684`. Provider capture metadata and all paths are preserved in the linked configuration and JSON.

Current Google query: 2026-11-20T15:54:46.887282Z. Raw API duration 36.37 min; query-clock to provider destination-arrival-plus-egress 37.90 min. These present-day values differ and neither is used as an October outcome.

Primary event representatives: **24**; all confirmed checkpoints: **158**.

Primary manual impact counts: {'DISRUPTION': 24}. All-checkpoint manual impact counts: {'DISRUPTION': 158}.

| Cohort | Mode | Advice scope | Actions | Scorable Switch | Gains / ties / losses | Unknown Switch | Same-station-path Switch | Different-path Switch |
|---|---|---|---|---:|---|---:|---:|---:|
| primary_summary | mta | strict_decision | {'UNDETERMINED': 20, 'SWITCH': 4} | 2 | 1 / 1 / 0 | 2 | 0 | 4 |
| primary_summary | mta | conditional_timing_decision | {'UNDETERMINED': 20, 'SWITCH': 4} | 2 | 1 / 1 / 0 | 2 | 0 | 4 |
| primary_summary | time_profile | strict_decision | {'UNDETERMINED': 22, 'SWITCH': 2} | 1 | 1 / 0 / 0 | 1 | 0 | 2 |
| primary_summary | time_profile | conditional_timing_decision | {'UNDETERMINED': 22, 'SWITCH': 2} | 1 | 1 / 0 / 0 | 1 | 0 | 2 |
| primary_summary | incident_profile | strict_decision | {'UNDETERMINED': 21, 'SWITCH': 3} | 1 | 1 / 0 / 0 | 2 | 0 | 3 |
| primary_summary | incident_profile | conditional_timing_decision | {'UNDETERMINED': 21, 'SWITCH': 3} | 1 | 1 / 0 / 0 | 2 | 0 | 3 |
| all_checkpoint_summary | mta | strict_decision | {'UNDETERMINED': 132, 'SWITCH': 26} | 11 | 10 / 1 / 0 | 15 | 0 | 26 |
| all_checkpoint_summary | mta | conditional_timing_decision | {'UNDETERMINED': 127, 'SWITCH': 31} | 12 | 11 / 1 / 0 | 19 | 0 | 31 |
| all_checkpoint_summary | time_profile | strict_decision | {'UNDETERMINED': 147, 'SWITCH': 11} | 5 | 4 / 1 / 0 | 6 | 0 | 11 |
| all_checkpoint_summary | time_profile | conditional_timing_decision | {'UNDETERMINED': 144, 'SWITCH': 14} | 6 | 5 / 1 / 0 | 8 | 0 | 14 |
| all_checkpoint_summary | incident_profile | strict_decision | {'UNDETERMINED': 139, 'SWITCH': 19} | 10 | 6 / 4 / 0 | 9 | 0 | 19 |
| all_checkpoint_summary | incident_profile | conditional_timing_decision | {'UNDETERMINED': 133, 'SWITCH': 25} | 11 | 7 / 4 / 0 | 14 | 0 | 25 |

### Every primary event: incident-profile mode

| Historical cutoff | Official incident | Advice | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---|---:|
| 2026-10-25T19:37:22.724000-04:00 | lmm:alert:273450 | UNDETERMINED | research_r_direct | unknown / 53.75 | unknown / 59.54 | unknown |
| 2026-10-25T21:13:22.702000-04:00 | lmm:alert:273460 | UNDETERMINED | research_e_c | unknown / 50.32 | unknown / unknown | unknown |
| 2026-10-26T02:21:38.591000-04:00 | lmm:alert:273474 | UNDETERMINED | research_7_4 | unknown / 68.53 | unknown / unknown | unknown |
| 2026-10-26T07:07:23.783000-04:00 | lmm:alert:273501 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 39.57 / 41.11 | unknown / 46.34 | unknown |
| 2026-10-26T08:56:30.639000-04:00 | lmm:alert:273515 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 37.91 / 35.99 | unknown / 34.67 | unknown |
| 2026-10-26T11:22:28.590000-04:00 | lmm:alert:273528 | UNDETERMINED | research_e_c | 41.70 / 43.64 | 47.26 / unknown | unknown |
| 2026-10-26T13:37:30.637000-04:00 | lmm:alert:273540 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 44.00 / 40.10 | unknown / 38.39 | unknown |
| 2026-10-26T15:31:55.537000-04:00 | lmm:alert:273555 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 43.17 / 41.83 | unknown / 38.97 | unknown |
| 2026-10-26T16:04:51.133000-04:00 | lmm:alert:273561 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 43.69 / 44.44 | unknown / 42.90 | unknown |
| 2026-10-28T08:56:52.722000-04:00 | lmm:alert:273822 | SWITCH | google-route-88aa6b135b2fe15e2cd08a95 | 42.17 / 35.62 | unknown / unknown | unknown |
| 2026-10-28T10:31:05.551000-04:00 | lmm:alert:273835 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 38.52 / 42.34 | unknown / 42.26 | unknown |
| 2026-10-28T14:12:55.633000-04:00 | lmm:alert:273862 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 40.06 / 41.58 | unknown / 44.02 | unknown |
| 2026-10-28T16:28:12.734000-04:00 | lmm:alert:273875 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 40.11 / 38.02 | 38.07 / 39.39 | -1.32 |
| 2026-10-28T21:27:45.542000-04:00 | lmm:alert:273920 | SWITCH | google-route-88aa6b135b2fe15e2cd08a95 | 59.33 / 37.97 | 62.06 / 38.47 | 23.58 |
| 2026-10-29T14:26:42.725000-04:00 | lmm:alert:274010 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 39.04 / 36.55 | unknown / 34.77 | unknown |
| 2026-10-29T15:08:45.544000-04:00 | lmm:alert:274020 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 43.60 / 39.24 | unknown / 38.97 | unknown |
| 2026-10-29T19:53:47.736000-04:00 | lmm:alert:274063 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 38.17 / 37.43 | unknown / 42.29 | unknown |
| 2026-10-29T20:57:00.636000-04:00 | lmm:alert:274074 | SWITCH | google-route-88aa6b135b2fe15e2cd08a95 | 87.18 / 37.99 | unknown / 35.89 | unknown |
| 2026-10-30T07:01:20.639000-04:00 | lmm:alert:274139 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 37.77 / 41.41 | 39.84 / 37.67 | 2.17 |
| 2026-10-30T08:25:42.730000-04:00 | lmm:alert:274148 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 43.97 / 43.29 | 42.35 / 42.80 | -0.45 |
| 2026-10-30T18:20:30.549000-04:00 | lmm:alert:274257 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | 38.53 / 36.72 | unknown / 38.07 | unknown |
| 2026-10-31T02:25:47.699000-04:00 | lmm:alert:274311 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | unknown / 43.70 | unknown / 40.31 | unknown |
| 2026-10-31T13:40:23.586000-04:00 | lmm:alert:274348 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | unknown / 39.53 | unknown / 39.39 | unknown |
| 2026-10-31T15:10:05.560000-04:00 | lmm:alert:274354 | UNDETERMINED | google-route-88aa6b135b2fe15e2cd08a95 | unknown / 45.11 | unknown / 42.97 | unknown |

### Complete per-route comparisons for available illustrations

The following are the earliest comparable forecast-best-alternative checkpoints per incident and manually qualified impact. Availability selects illustrations only; all gains, losses, abstentions and unknowns remain in the frozen cohorts above. A later illustration can differ from the primary event checkpoint.

#### 2026-10-26T09:01:30.639000-04:00

Incident lmm:alert:273515. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 37.66 | 49.17 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 40.33 | 42.51 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 58.33 | 53.94 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 47.82 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 51.08 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 4 via Grand Central | OTHER_PATH | 49.04 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 53.49 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 52.88 | 51.92 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 51.68 | 50.04 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 58.28 | 53.94 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 68.50 | 70.52 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-26T11:27:28.590000-04:00

Incident lmm:alert:273528. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 40.70 | 46.51 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 40.46 | 39.17 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 55.66 | 54.61 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 52.50 | 50.17 | INFERRED |
| E to C via Port Authority | OTHER_PATH | 53.60 | 53.54 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 56.64 | 54.32 | INFERRED |
| 7 to 5 via Grand Central | OTHER_PATH | 66.19 | 65.49 | INFERRED |
| 7 to 2 via Times Sq | OTHER_PATH | 56.72 | 57.44 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 59.34 | 60.31 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 55.69 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| W to R via Herald Sq | OTHER_PATH | 61.97 | 60.61 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-26T15:00:22.730000-04:00

Incident lmm:alert:273540. Manual impact DISRUPTION. Strict advice SWITCH; conditional timing advice SWITCH.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 45.22 | 51.60 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 40.13 | 37.72 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 56.28 | 53.87 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 43.71 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 45.06 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 4 via Grand Central | OTHER_PATH | 48.96 | 58.49 | INFERRED |
| 7 to 5 via Grand Central | OTHER_PATH | 46.02 | 55.35 | INFERRED |
| 7 to 2 via Times Sq | OTHER_PATH | 51.59 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 3 via Times Sq | OTHER_PATH | 49.77 | 53.60 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 67.04 | 64.97 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 67.04 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-26T15:41:55.537000-04:00

Incident lmm:alert:273555. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 41.52 | 47.41 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 42.33 | 38.74 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 62.19 | 62.26 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 43.37 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 52.08 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 4 via Grand Central | OTHER_PATH | 54.73 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 54.92 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 57.24 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 3 via Times Sq | OTHER_PATH | 50.23 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| N to R via Herald Sq | OTHER_PATH | 62.19 | 62.26 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 62.19 | 62.26 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-26T16:14:51.133000-04:00

Incident lmm:alert:273561. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 45.52 | 53.55 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 42.88 | 43.65 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 57.81 | 55.65 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 47.33 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 48.99 | 54.96 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 49.55 | 49.08 | INFERRED |
| 7 to 5 via Grand Central | OTHER_PATH | 53.23 | 51.23 | INFERRED |
| 7 to 2 via Times Sq | OTHER_PATH | 56.30 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 3 via Times Sq | OTHER_PATH | 53.99 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| N to R via Herald Sq | OTHER_PATH | 67.56 | 64.81 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 57.76 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-28T09:06:52.722000-04:00

Incident lmm:alert:273822. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 39.62 | 44.34 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 40.12 | 44.55 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 52.83 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to A via Port Authority | OTHER_PATH | 41.35 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 48.03 | 54.67 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 57.06 | 54.32 | INFERRED |
| 7 to 5 via Grand Central | OTHER_PATH | 61.48 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 61.90 | 58.72 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 61.81 | 55.47 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 61.93 | 64.17 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 70.13 | 66.42 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-28T10:34:00.543000-04:00

Incident lmm:alert:273835. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 40.80 | 38.51 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 39.42 | 39.34 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 55.03 | 57.11 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 49.62 | 48.82 | INFERRED |
| E to C via Port Authority | OTHER_PATH | 53.38 | 53.17 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 44.88 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 44.40 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 54.09 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 3 via Times Sq | OTHER_PATH | 49.63 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| N to R via Herald Sq | OTHER_PATH | 69.32 | 67.01 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-28T14:17:20.635000-04:00

Incident lmm:alert:273862. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 39.85 | 47.02 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 37.16 | 39.61 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 54.19 | 54.86 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 45.80 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 46.00 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 4 via Grand Central | OTHER_PATH | 55.03 | 58.52 | INFERRED |
| 7 to 5 via Grand Central | OTHER_PATH | 54.61 | 56.49 | INFERRED |
| 7 to 2 via Times Sq | OTHER_PATH | 62.45 | 59.89 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 57.81 | 57.21 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 61.62 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| W to R via Herald Sq | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-28T16:28:12.734000-04:00

Incident lmm:alert:273875. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 40.11 | 38.07 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 38.02 | 39.39 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 58.02 | 59.59 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 46.94 | 46.30 | INFERRED |
| E to C via Port Authority | OTHER_PATH | 57.67 | 55.65 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 56.77 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 60.23 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 59.47 | 70.04 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 53.63 | 53.82 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 58.12 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| W to R via Herald Sq | OTHER_PATH | 64.78 | 67.65 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

Primary-case walk sensitivity: 8/8 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-484.0, 41.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-28T21:27:45.542000-04:00

Incident lmm:alert:273920. Manual impact DISRUPTION. Strict advice SWITCH; conditional timing advice SWITCH.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 59.33 | 62.06 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 37.97 | 38.47 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E to A via Port Authority | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E to C via Port Authority | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| 7 to 4 via Grand Central | OTHER_PATH | 43.91 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 5 via Grand Central | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| 7 to 2 via Times Sq | OTHER_PATH | 57.50 | 54.69 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 54.46 | 51.86 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 73.38 | 73.69 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

Primary-case walk sensitivity: 8/8 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [1295.0, 1644.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-29T14:41:42.725000-04:00

Incident lmm:alert:274010. Manual impact DISRUPTION. Strict advice SWITCH; conditional timing advice SWITCH.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 43.48 | 39.82 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 38.30 | 36.85 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 54.16 | 52.04 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 53.51 | 54.15 | INFERRED |
| E to C via Port Authority | OTHER_PATH | 55.80 | 55.85 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 55.12 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 54.34 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 55.15 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 3 via Times Sq | OTHER_PATH | 59.44 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| N to R via Herald Sq | OTHER_PATH | 68.08 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| W to R via Herald Sq | OTHER_PATH | 68.08 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-29T15:23:45.544000-04:00

Incident lmm:alert:274020. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 43.60 | 40.72 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 41.24 | 37.72 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 64.28 | 63.91 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 44.48 | 46.07 | INFERRED |
| E to C via Port Authority | OTHER_PATH | 52.25 | 55.74 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 48.58 | 50.02 | INFERRED |
| 7 to 5 via Grand Central | OTHER_PATH | 51.79 | 53.46 | INFERRED |
| 7 to 2 via Times Sq | OTHER_PATH | 54.00 | 52.36 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 52.39 | 54.16 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 64.21 | 63.91 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 64.21 | 63.91 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-30T07:01:20.639000-04:00

Incident lmm:alert:274139. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 37.77 | 39.84 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 41.41 | 37.67 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 62.74 | 64.61 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 47.41 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 47.21 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 4 via Grand Central | OTHER_PATH | 51.57 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 45.96 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 54.73 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 3 via Times Sq | OTHER_PATH | 49.35 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| N to R via Herald Sq | OTHER_PATH | 62.70 | 64.61 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 62.70 | 64.61 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

Primary-case walk sensitivity: 8/8 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [10.0, 255.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-30T08:25:42.730000-04:00

Incident lmm:alert:274148. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 43.97 | 42.35 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 43.29 | 42.80 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 56.69 | 53.95 | INFERRED |
| E to A via Port Authority | OTHER_PATH | 60.19 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E to C via Port Authority | OTHER_PATH | 61.75 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 4 via Grand Central | OTHER_PATH | 54.54 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 56.72 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 46.98 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 3 via Times Sq | OTHER_PATH | 51.98 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| N to R via Herald Sq | OTHER_PATH | 69.30 | 66.04 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 56.65 | 53.95 | INFERRED |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

Primary-case walk sensitivity: 7/8 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-147.0, 528.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-30T18:25:30.549000-04:00

Incident lmm:alert:274257. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| F: Court Sq-23 St to Jay St-MetroTech | STAY | 38.78 | 52.07 | INFERRED |
| G: Court Sq to Hoyt-Schermerhorn Sts | OTHER_PATH | 39.97 | 39.57 | INFERRED |
| R Queens Plaza to Jay St | OTHER_PATH | 62.39 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| E to A via Port Authority | OTHER_PATH | 53.12 | 54.39 | INFERRED |
| E to C via Port Authority | OTHER_PATH | 55.37 | 56.16 | INFERRED |
| 7 to 4 via Grand Central | OTHER_PATH | 49.38 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 5 via Grand Central | OTHER_PATH | 49.59 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Sq | OTHER_PATH | 50.14 | 49.77 | INFERRED |
| 7 to 3 via Times Sq | OTHER_PATH | 51.33 | 51.92 | INFERRED |
| N to R via Herald Sq | OTHER_PATH | 62.49 | 61.26 | INFERRED |
| W to R via Herald Sq | OTHER_PATH | 70.03 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| E then A (provider route unavailable) | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

## grandcentral_boroughhall

East 42nd Street and Lexington Avenue, Manhattan, New York, NY → Brooklyn Borough Hall, 209 Joralemon Street, Brooklyn, NY 11201.

Google-defined Stay: `google-route-54502e7253ac53a2be3cd264`. Provider capture metadata and all paths are preserved in the linked configuration and JSON.

Current Google query: 2026-11-20T15:54:46.887438Z. Raw API duration 23.95 min; query-clock to provider destination-arrival-plus-egress 31.60 min. These present-day values differ and neither is used as an October outcome.

Primary event representatives: **20**; all confirmed checkpoints: **132**.

Primary manual impact counts: {'DISRUPTION': 20}. All-checkpoint manual impact counts: {'DISRUPTION': 131, 'SEVERE': 1}.

| Cohort | Mode | Advice scope | Actions | Scorable Switch | Gains / ties / losses | Unknown Switch | Same-station-path Switch | Different-path Switch |
|---|---|---|---|---:|---|---:|---:|---:|
| primary_summary | mta | strict_decision | {'STAY': 16, 'UNDETERMINED': 3, 'SWITCH': 1} | 0 | 0 / 0 / 0 | 1 | 1 | 0 |
| primary_summary | mta | conditional_timing_decision | {'STAY': 16, 'UNDETERMINED': 3, 'SWITCH': 1} | 0 | 0 / 0 / 0 | 1 | 1 | 0 |
| primary_summary | time_profile | strict_decision | {'STAY': 15, 'UNDETERMINED': 3, 'SWITCH': 2} | 0 | 0 / 0 / 0 | 2 | 2 | 0 |
| primary_summary | time_profile | conditional_timing_decision | {'STAY': 15, 'UNDETERMINED': 3, 'SWITCH': 2} | 0 | 0 / 0 / 0 | 2 | 2 | 0 |
| primary_summary | incident_profile | strict_decision | {'STAY': 16, 'UNDETERMINED': 3, 'SWITCH': 1} | 0 | 0 / 0 / 0 | 1 | 1 | 0 |
| primary_summary | incident_profile | conditional_timing_decision | {'STAY': 16, 'UNDETERMINED': 3, 'SWITCH': 1} | 0 | 0 / 0 / 0 | 1 | 1 | 0 |
| all_checkpoint_summary | mta | strict_decision | {'STAY': 62, 'SWITCH': 29, 'UNDETERMINED': 41} | 10 | 9 / 1 / 0 | 19 | 26 | 3 |
| all_checkpoint_summary | mta | conditional_timing_decision | {'STAY': 75, 'SWITCH': 33, 'UNDETERMINED': 24} | 12 | 10 / 2 / 0 | 21 | 30 | 3 |
| all_checkpoint_summary | time_profile | strict_decision | {'STAY': 63, 'SWITCH': 28, 'UNDETERMINED': 41} | 10 | 9 / 1 / 0 | 18 | 27 | 1 |
| all_checkpoint_summary | time_profile | conditional_timing_decision | {'STAY': 75, 'SWITCH': 33, 'UNDETERMINED': 24} | 12 | 10 / 2 / 0 | 21 | 30 | 3 |
| all_checkpoint_summary | incident_profile | strict_decision | {'STAY': 68, 'SWITCH': 23, 'UNDETERMINED': 41} | 4 | 4 / 0 / 0 | 19 | 17 | 6 |
| all_checkpoint_summary | incident_profile | conditional_timing_decision | {'STAY': 80, 'SWITCH': 28, 'UNDETERMINED': 24} | 6 | 5 / 1 / 0 | 22 | 19 | 9 |

### Every primary event: incident-profile mode

| Historical cutoff | Official incident | Advice | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---|---:|
| 2026-10-26T09:49:28.593000-04:00 | lmm:alert:273523 | STAY | research_broadway_via_7 | 27.14 / 30.85 | 23.99 / unknown | unknown |
| 2026-10-26T10:39:30.546000-04:00 | lmm:alert:273527 | STAY | research_broadway_via_7 | 31.15 / 32.77 | 35.49 / unknown | unknown |
| 2026-10-26T15:26:45.545000-04:00 | lmm:alert:273553 | STAY | google-route-fae079d4a0a7051e64aa1cda | 23.83 / 23.80 | 28.91 / 26.66 | 2.25 |
| 2026-10-26T16:32:52.742000-04:00 | lmm:alert:273565 | STAY | google-route-fae079d4a0a7051e64aa1cda | 29.21 / 29.53 | 27.75 / 30.54 | -2.78 |
| 2026-10-26T17:01:22.713000-04:00 | lmm:alert:273573 | STAY | google-route-fae079d4a0a7051e64aa1cda | 25.67 / 27.10 | unknown / 29.87 | unknown |
| 2026-10-27T07:04:10.843000-04:00 | lmm:alert:273651 | STAY | google-route-fae079d4a0a7051e64aa1cda | 23.31 / 24.30 | 25.02 / 26.97 | -1.95 |
| 2026-10-27T08:04:03.779000-04:00 | lmm:alert:273660 | STAY | google-route-fae079d4a0a7051e64aa1cda | 23.59 / 30.84 | unknown / 27.37 | unknown |
| 2026-10-27T16:33:22.725000-04:00 | lmm:alert:273712 | STAY | google-route-fae079d4a0a7051e64aa1cda | 27.16 / 31.59 | unknown / unknown | unknown |
| 2026-10-28T02:07:43.590000-04:00 | lmm:alert:273775 | UNDETERMINED | research_broadway_via_7 | unknown / 35.68 | unknown / unknown | unknown |
| 2026-10-28T07:16:07.748000-04:00 | lmm:alert:273799 | STAY | google-route-fae079d4a0a7051e64aa1cda | 28.24 / 29.47 | 43.49 / unknown | unknown |
| 2026-10-28T10:21:58.608000-04:00 | lmm:alert:273834 | STAY | research_broadway_via_7 | 29.48 / 31.00 | 39.36 / 31.84 | 7.52 |
| 2026-10-28T16:37:05.640000-04:00 | lmm:alert:273870 | STAY | google-route-f64f3db98836328b08094801 | 26.21 / 30.36 | unknown / unknown | unknown |
| 2026-10-29T08:09:45.538000-04:00 | lmm:alert:273969 | STAY | google-route-fae079d4a0a7051e64aa1cda | 25.53 / 26.55 | 24.16 / 26.09 | -1.93 |
| 2026-10-29T09:50:43.580000-04:00 | lmm:alert:273981 | STAY | research_broadway_via_7 | 30.67 / 29.51 | 35.76 / 29.69 | 6.07 |
| 2026-10-29T15:11:12.776000-04:00 | lmm:alert:274016 | STAY | google-route-fae079d4a0a7051e64aa1cda | 28.08 / 26.19 | 36.05 / 33.97 | 2.08 |
| 2026-10-29T16:04:18.786000-04:00 | lmm:alert:274022 | STAY | google-route-fae079d4a0a7051e64aa1cda | 28.52 / 28.09 | 26.57 / 24.70 | 1.87 |
| 2026-10-29T17:40:20.552000-04:00 | lmm:alert:274037 | STAY | google-route-fae079d4a0a7051e64aa1cda | 25.78 / 27.20 | unknown / 32.27 | unknown |
| 2026-10-29T18:57:37.710000-04:00 | lmm:alert:274054 | SWITCH | google-route-fae079d4a0a7051e64aa1cda | 39.84 / 25.65 | unknown / 29.27 | unknown |
| 2026-10-29T23:10:47.738000-04:00 | lmm:alert:274092 | UNDETERMINED | google-route-fae079d4a0a7051e64aa1cda | unknown / 25.47 | unknown / 24.54 | unknown |
| 2026-10-31T13:17:27.714000-04:00 | lmm:alert:274347 | UNDETERMINED | google-route-fae079d4a0a7051e64aa1cda | unknown / 22.98 | unknown / 26.62 | unknown |

### Complete per-route comparisons for available illustrations

The following are the earliest comparable forecast-best-alternative checkpoints per incident and manually qualified impact. Availability selects illustrations only; all gains, losses, abstentions and unknowns remain in the frozen cohorts above. A later illustration can differ from the primary event checkpoint.

#### 2026-10-26T10:01:05.641000-04:00

Incident lmm:alert:273523. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 33.81 | 32.69 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 39.60 | 37.39 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 55.25 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 29.06 | 25.37 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 33.80 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 41.35 | 40.96 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 39.60 | 37.39 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 36.33 | 36.94 | INFERRED |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-26T10:44:30.546000-04:00

Incident lmm:alert:273527. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 29.93 | 30.49 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 50.03 | 58.82 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 54.35 | 61.52 | INFERRED |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 28.66 | 25.19 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 40.92 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 48.30 | 55.59 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 42.03 | 44.26 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 39.50 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-26T15:26:45.545000-04:00

Incident lmm:alert:273553. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 23.83 | 28.91 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 34.48 | 32.96 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 35.59 | 37.69 | INFERRED |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 23.80 | 26.66 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 41.59 | 36.44 | INFERRED |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 29.31 | 29.86 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 38.16 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 45.64 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |

Primary-case walk sensitivity: 5/6 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-104.0, 592.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-26T16:32:52.742000-04:00

Incident lmm:alert:273565. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 29.21 | 27.75 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 44.16 | 48.85 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 38.98 | 49.82 | INFERRED |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 29.53 | 30.54 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 33.40 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 34.17 | 33.20 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 40.21 | 37.92 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 38.98 | 49.82 | INFERRED |

Primary-case walk sensitivity: 6/6 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-287.0, -47.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-26T17:02:22.729000-04:00

Incident lmm:alert:273573. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 30.16 | 33.19 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 37.06 | 36.55 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 66.27 | 70.02 | INFERRED |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 26.69 | 28.87 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 40.33 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 34.76 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 44.16 | 43.27 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 37.22 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-27T07:04:10.843000-04:00

Incident lmm:alert:273651. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 23.31 | 25.02 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 66.22 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 68.65 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 24.30 | 26.97 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 40.85 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 64.85 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 37.96 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 40.05 | 39.87 | INFERRED |

Primary-case walk sensitivity: 6/6 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-448.0, 149.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-27T16:48:22.725000-04:00

Incident lmm:alert:273712. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 26.51 | 45.97 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 36.36 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 50.05 | 49.24 | INFERRED |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 30.61 | 54.29 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 36.37 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 34.52 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 41.05 | 43.00 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 36.52 | 39.49 | INFERRED |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-28T09:09:25.639000-04:00

Incident lmm:alert:273799. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 32.98 | 27.02 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 33.81 | 35.36 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 49.12 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 39.10 | 36.99 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 33.83 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 33.01 | 30.46 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 40.11 | 39.67 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 37.78 | 42.34 | INFERRED |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-28T10:21:58.608000-04:00

Incident lmm:alert:273834. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 29.48 | 39.36 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 32.78 | 62.02 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 32.68 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 31.68 | 31.11 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 38.15 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 31.00 | 31.84 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 40.07 | 73.17 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 44.28 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |

Primary-case walk sensitivity: 7/7 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [331.0, 571.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-29T08:09:45.538000-04:00

Incident lmm:alert:273969. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 25.53 | 24.16 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 35.48 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 32.64 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 26.55 | 26.09 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 42.07 | 40.69 | INFERRED |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 27.56 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 39.40 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 39.15 | 38.61 | INFERRED |

Primary-case walk sensitivity: 6/6 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-236.0, 4.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-29T09:50:43.580000-04:00

Incident lmm:alert:273981. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 30.67 | 35.76 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 36.76 | 36.54 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 40.24 | 36.31 | INFERRED |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 31.56 | 38.41 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 31.47 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 29.51 | 29.69 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 41.40 | 38.51 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 40.24 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |

Primary-case walk sensitivity: 7/7 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [244.0, 484.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-29T15:11:12.776000-04:00

Incident lmm:alert:274016. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 28.08 | 36.05 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 26.83 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 39.55 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 26.19 | 33.97 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 37.63 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 45.98 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 42.14 | 41.12 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 39.55 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |

Primary-case walk sensitivity: 6/6 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [5.0, 245.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-29T16:04:18.786000-04:00

Incident lmm:alert:274022. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 28.52 | 26.57 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 32.93 | 31.54 | INFERRED |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 47.08 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 28.09 | 24.70 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 37.43 | 40.89 | INFERRED |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 38.71 | 34.80 | INFERRED |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 38.65 | 37.60 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 40.07 | 40.47 | INFERRED |

Primary-case walk sensitivity: 6/6 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-8.0, 232.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-29T17:43:32.707000-04:00

Incident lmm:alert:274037. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 28.66 | 30.89 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 36.23 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 49.78 | 49.34 | INFERRED |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 26.06 | 29.07 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 36.90 | 36.25 | INFERRED |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 33.92 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 41.28 | 40.05 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 41.13 | 43.15 | INFERRED |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

#### 2026-10-29T19:07:37.710000-04:00

Incident lmm:alert:274054. Manual impact DISRUPTION. Strict advice SWITCH; conditional timing advice SWITCH.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 5: Grand Central-42 St to Borough Hall | STAY | 36.94 | 34.49 | INFERRED |
| 7 then 3: Grand Central-42 St to Borough Hall | OTHER_PATH | 39.91 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 7 then F: Grand Central-42 St to Jay St-MetroTech | OTHER_PATH | 51.18 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| 4: Grand Central-42 St to Borough Hall | SAME_STATION_PATH | 23.53 | 31.05 | INFERRED |
| 6 then R: Grand Central-42 St to Court St | OTHER_PATH | 31.97 | unknown | INFERRED_DEPARTURE_BEFORE_PLATFORM_READY |
| 7 to 2 via Times Square (research library service variant) | OTHER_PATH | 39.04 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |
| Walk to Times Square, then 2 or 3 to Borough Hall | OTHER_PATH | 39.04 | 37.64 | INFERRED |
| Walk to Bryant Park, F to Jay Street, walk to Borough Hall | OTHER_PATH | 37.53 | unknown | MISSING_OR_UNUSABLE_ENDPOINT_LABEL |

This illustration is not the primary checkpoint; the predeclared walking sensitivity applies to the separately identified primary event representative.

## courtsquare_timessquare

Court Square Park, Long Island City, NY → West 42nd Street and Seventh Avenue, Manhattan, New York, NY.

Google-defined Stay: `google-route-9a6888e689fb501e230ccda5`. Provider capture metadata and all paths are preserved in the linked configuration and JSON.

Current Google query: 2026-11-20T15:54:46.886885Z. Raw API duration 14.63 min; query-clock to provider destination-arrival-plus-egress 18.35 min. These present-day values differ and neither is used as an October outcome.

Primary event representatives: **5**; all confirmed checkpoints: **32**.

Primary manual impact counts: {'DISRUPTION': 5}. All-checkpoint manual impact counts: {'DISRUPTION': 29, 'SEVERE': 3}.

| Cohort | Mode | Advice scope | Actions | Scorable Switch | Gains / ties / losses | Unknown Switch | Same-station-path Switch | Different-path Switch |
|---|---|---|---|---:|---|---:|---:|---:|
| primary_summary | mta | strict_decision | {'UNDETERMINED': 4, 'STAY': 1} | 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| primary_summary | mta | conditional_timing_decision | {'UNDETERMINED': 4, 'STAY': 1} | 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| primary_summary | time_profile | strict_decision | {'UNDETERMINED': 3, 'STAY': 1, 'SWITCH': 1} | 1 | 0 / 1 / 0 | 0 | 0 | 1 |
| primary_summary | time_profile | conditional_timing_decision | {'SWITCH': 2, 'UNDETERMINED': 2, 'STAY': 1} | 2 | 0 / 1 / 1 | 0 | 0 | 2 |
| primary_summary | incident_profile | strict_decision | {'UNDETERMINED': 4, 'STAY': 1} | 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| primary_summary | incident_profile | conditional_timing_decision | {'UNDETERMINED': 4, 'STAY': 1} | 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| all_checkpoint_summary | mta | strict_decision | {'UNDETERMINED': 27, 'STAY': 5} | 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| all_checkpoint_summary | mta | conditional_timing_decision | {'UNDETERMINED': 24, 'STAY': 8} | 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| all_checkpoint_summary | time_profile | strict_decision | {'UNDETERMINED': 26, 'STAY': 3, 'SWITCH': 3} | 2 | 1 / 1 / 0 | 1 | 0 | 3 |
| all_checkpoint_summary | time_profile | conditional_timing_decision | {'SWITCH': 5, 'UNDETERMINED': 21, 'STAY': 6} | 4 | 1 / 1 / 2 | 1 | 0 | 5 |
| all_checkpoint_summary | incident_profile | strict_decision | {'UNDETERMINED': 27, 'STAY': 3, 'SWITCH': 2} | 1 | 1 / 0 / 0 | 1 | 0 | 2 |
| all_checkpoint_summary | incident_profile | conditional_timing_decision | {'UNDETERMINED': 23, 'SWITCH': 3, 'STAY': 6} | 2 | 2 / 0 / 0 | 1 | 0 | 3 |

### Every primary event: incident-profile mode

| Historical cutoff | Official incident | Advice | Forecast-best alternative | Predicted Stay / alternative, min | Proxy Stay / alternative, min | Proxy saving, min |
|---|---|---|---|---|---|---:|
| 2026-10-25T19:00:23.587000-04:00 | lmm:alert:273447 | UNDETERMINED | google-route-b0b73137413b2a2d691f0c66 | 24.11 / 25.44 | 20.69 / 29.07 | -8.38 |
| 2026-10-25T23:22:13.586000-04:00 | lmm:alert:273468 | UNDETERMINED | google-route-b0b73137413b2a2d691f0c66 | 16.44 / 32.77 | 16.36 / 30.16 | -13.80 |
| 2026-10-30T05:36:23.617000-04:00 | lmm:alert:274118 | STAY | google-route-59e8e3290ecae4779e70fb80 | 15.13 / 23.63 | 112.92 / 22.77 | 90.15 |
| 2026-10-30T22:11:57.712000-04:00 | lmm:alert:274290 | UNDETERMINED | google-route-b0b73137413b2a2d691f0c66 | 20.65 / 24.93 | 20.34 / 24.84 | -4.50 |
| 2026-10-31T10:46:27.718000-04:00 | lmm:alert:274337 | UNDETERMINED | google-route-b0b73137413b2a2d691f0c66 | 27.32 / 23.33 | 23.37 / 21.92 | 1.45 |

### Complete per-route comparisons for available illustrations

The following are the earliest comparable forecast-best-alternative checkpoints per incident and manually qualified impact. Availability selects illustrations only; all gains, losses, abstentions and unknowns remain in the frozen cohorts above. A later illustration can differ from the primary event checkpoint.

#### 2026-10-25T19:00:23.587000-04:00

Incident lmm:alert:273447. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 7: Court Sq to Times Sq-42 St | STAY | 24.11 | 20.69 | INFERRED |
| F: Court Sq-23 St to 42 St-Bryant Pk | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E: Court Sq-23 St to 42 St-Port Authority Bus Terminal | OTHER_PATH | 25.44 | 29.07 | INFERRED |

Primary-case walk sensitivity: 7/7 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-623.0, -383.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-25T23:22:13.586000-04:00

Incident lmm:alert:273468. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 7: Court Sq to Times Sq-42 St | STAY | 16.44 | 16.36 | INFERRED |
| F: Court Sq-23 St to 42 St-Bryant Pk | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E: Court Sq-23 St to 42 St-Port Authority Bus Terminal | OTHER_PATH | 32.77 | 30.16 | INFERRED |

Primary-case walk sensitivity: 7/7 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-948.0, -708.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-30T05:36:23.617000-04:00

Incident lmm:alert:274118. Manual impact DISRUPTION. Strict advice STAY; conditional timing advice STAY.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 7: Court Sq to Times Sq-42 St | STAY | 15.13 | 112.92 | INFERRED |
| F: Court Sq-23 St to 42 St-Bryant Pk | OTHER_PATH | 23.63 | 22.77 | INFERRED |
| E: Court Sq-23 St to 42 St-Port Authority Bus Terminal | OTHER_PATH | 29.97 | 35.74 | INFERRED |

Primary-case walk sensitivity: 7/7 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-640.0, 5529.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-30T22:11:57.712000-04:00

Incident lmm:alert:274290. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 7: Court Sq to Times Sq-42 St | STAY | 20.65 | 20.34 | INFERRED |
| F: Court Sq-23 St to 42 St-Bryant Pk | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E: Court Sq-23 St to 42 St-Port Authority Bus Terminal | OTHER_PATH | 24.93 | 24.84 | INFERRED |

Primary-case walk sensitivity: 7/7 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-390.0, 60.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

#### 2026-10-31T10:46:27.718000-04:00

Incident lmm:alert:274337. Manual impact DISRUPTION. Strict advice UNDETERMINED; conditional timing advice UNDETERMINED.

| Candidate | Path relation to Stay | Predicted min | Final proxy min | Outcome status / reason |
|---|---|---:|---:|---|
| 7: Court Sq to Times Sq-42 St | STAY | 27.32 | 23.37 | INFERRED |
| F: Court Sq-23 St to 42 St-Bryant Pk | OTHER_PATH | unknown | unknown | NO_COMPLETE_FORECAST_SELECTED_JOURNEY |
| E: Court Sq-23 St to 42 St-Port Authority Bus Terminal | OTHER_PATH | 23.33 | 21.92 | INFERRED |

Primary-case walk sensitivity: 5/7 variants preserve strict advice; comparable forecast-best-alternative saving range, seconds: [-33.0, 207.0]. Full variants retain selected trains and proxy quality in the ignored evidence artifact.

## Reproduce

```sh
.venv/bin/python algo/scripts/evaluate_google_corridors.py --prepare-inputs
# Complete the input-only text review before freezing.
.venv/bin/python algo/scripts/evaluate_google_corridors.py --freeze-only
.venv/bin/python algo/scripts/evaluate_google_corridors.py
```

Full results: `google-corridors-test.json`; selection, review, source hashes and ignored local evidence paths are retained beside this report. No general success-rate or untouched-test generalization is established by selected exploratory incidents.
