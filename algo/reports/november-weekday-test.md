# November weekday Stay/Switch results

Primary reporting dates: **November 2–6, 9–13 and 16–18, 2026**, 13 Monday–Friday dates in New York. The user requested this calendar view before outcome scoring. The October 1–31 model, five fixed Google Stay paths, 29 supplied paths in total, thresholds, original two-hour incident windows and prediction method are unchanged. November 19 is outcome boundary evidence only.

November 2–15 overlaps prior project exploration. November 16–18 is shown separately; the complete period is not claimed to be an untouched final test. Current Google minutes are not historical outcomes or proof that Stay was historically fastest. Raw-MTA actions are this project's rule applied to unmodified forecasts, not official MTA routing advice.

Exposure means a text-qualified unplanned service problem on Stay, including some unplanned service changes; it does not establish that the particular selected train's ETA worsened. Severe exposure distinguishes explicit severe wording from an official notice describing complete unplanned loss of the fixed through path. This is notice evidence, not independent proof of physical closure; through-service forecast conflicts remain recorded in the notice review. Closure cases with no usable Stay forecast remain unknown. Mixed planned closure mentions retain input-reviewed active/inactive/unknown timing and are not attributed to an unplanned cause.

Outcomes use exact forecast-selected trains, screened final MTA prediction proxies and declared walking times. Every needed endpoint requires a matching identity, archived confirmation and last observation within 180 seconds. A missed selected train is an operational failure with unknown complete travel time. A predicted gain of at least 5 minutes triggers Switch; outcome differences within ±3 minutes are practical ties.

## Main outcome counts

| Scope | Checkpoints | Corridor/publisher families | Unique publisher IDs | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All weekday checkpoints | 2306 | 197 | 178 | 287 | 99 | 16 | 2 | 170 |
| Weekday representatives | 197 | 197 | 178 | 34 | 11 | 1 | 1 | 21 |
| November 16–18 | 442 | 42 | 38 | 53 | 10 | 6 | 0 | 37 |
| November 16–18 representatives | 42 | 42 | 38 | 8 | 2 | 0 | 0 | 6 |
| Qualified severe weekday checkpoints | 183 | 12 | 11 | 34 | 10 | 1 | 0 | 23 |

The primary representative is recomputed from weekday inputs for each corridor/publisher incident family; it is not a filtered copy of the old all-date primary list. Repeated checkpoints, train pairs and publisher IDs are not independent causal incidents or passenger journeys. Different publisher families can describe a shared underlying problem; the input notice audit records such links without changing frozen grouping.

## Comparison against the raw-MTA policy

| Scope / comparison | Eligible actions | Comparable | Faster >3 min | Tie | Slower >3 min | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekday checkpoints / time_vs_mta | 991 | 690 | 49 | 638 | 3 | 301 |
| All weekday checkpoints / incident_vs_mta | 992 | 641 | 56 | 574 | 11 | 351 |
| All weekday checkpoints / incident_vs_time | 1004 | 664 | 12 | 642 | 10 | 340 |
| Weekday representatives / time_vs_mta | 116 | 89 | 7 | 82 | 0 | 27 |
| Weekday representatives / incident_vs_mta | 117 | 81 | 7 | 73 | 1 | 36 |
| Weekday representatives / incident_vs_time | 115 | 79 | 0 | 78 | 1 | 36 |
| November 16–18 / time_vs_mta | 188 | 124 | 9 | 115 | 0 | 64 |
| November 16–18 / incident_vs_mta | 187 | 107 | 8 | 97 | 2 | 80 |
| November 16–18 / incident_vs_time | 191 | 113 | 1 | 110 | 2 | 78 |
| November 16–18 representatives / time_vs_mta | 26 | 20 | 1 | 19 | 0 | 6 |
| November 16–18 representatives / incident_vs_mta | 26 | 18 | 1 | 16 | 1 | 8 |
| November 16–18 representatives / incident_vs_time | 26 | 18 | 0 | 17 | 1 | 8 |

Each comparison uses the actual journey selected by each policy, including its chosen train sequence. It does not substitute the unconditional fastest raw-MTA candidate.

## Raw-MTA Stay / model Switch

| Scope | Recommendations | Comparable | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| All weekday checkpoints | 58 | 22 | 13 | 9 | 0 | 36 |
| Weekday representatives | 7 | 2 | 1 | 1 | 0 | 5 |
| November 16–18 | 11 | 3 | 1 | 2 | 0 | 8 |
| November 16–18 representatives | 2 | 0 | 0 | 0 | 0 | 2 |

## Five-corridor weekday detail

| Corridor | Checkpoints | Families | Model Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|
| pilot_hayden_tandon | 691 | 63 | 74 | 33 | 3 | 1 | 37 |
| grandcentral_boroughhall | 479 | 37 | 92 | 22 | 6 | 0 | 64 |
| courtsquare_timessquare | 156 | 13 | 27 | 4 | 1 | 1 | 21 |
| timesquare_boroughhall | 362 | 38 | 63 | 32 | 3 | 0 | 28 |
| portauthority_tandon | 618 | 46 | 31 | 8 | 3 | 0 | 20 |

| Corridor | Acceptable Stay | Stay with known missed opportunity | Unknown Stay | Known missed selected journeys |
|---|---:|---:|---:|---:|
| pilot_hayden_tandon | 0 | 0 | 0 | 8 |
| grandcentral_boroughhall | 1 | 13 | 195 | 53 |
| courtsquare_timessquare | 8 | 9 | 50 | 18 |
| timesquare_boroughhall | 58 | 30 | 104 | 33 |
| portauthority_tandon | 116 | 15 | 150 | 25 |

Acceptable Stay requires complete outcomes for all forecast-eligible supplied candidates. A known faster alternative establishes a missed opportunity even when other outcomes are missing. These are fixed-selected-journey comparisons, not exhaustive navigation or proof against an adaptive passenger taking another earlier train on Stay.

The [machine-readable weekday report](november-weekday-test.json) includes every case, all three modes, primary and date-specific counts, severe evidence bases and planned-closure timing strata. The [calendar view freeze](november-weekday-selection-frozen.json) binds the exact input-selected case IDs. The [all-date input inventory](november-2026-candidate-selection.json) and full notice review remain secondary audit evidence. Weekend raw Stay forecasts exist for scope auditing only; weekend three-mode performance and outcomes were not scored.
