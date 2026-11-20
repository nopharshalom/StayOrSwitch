# November weekday corridor ETA error by daily period

This descriptive analysis uses the same five previously selected corridors and
their fixed Google Stay paths. It keeps every departure checkpoint independent
of later outcome availability and does not fit or change the October model.
The historical route is selected using archived MTA predictions; Google's
November 20 duration is not a historical label.

The final user-requested reporting scope is **weekdays only: November 2–6,
9–13 and 16–18, 2026**. Primary outputs contain 2,860 departure checkpoints,
195 daily cells and 15 pooled corridor/period cells. The previously frozen
3,960-row all-date input grid remains unchanged as secondary audit evidence;
the final scoring wrapper reads only the thirteen weekday label files.

| Corridor | Fixed Stay path |
|---|---|
| Hayden LIC Apartments to NYU Tandon | F, Court Sq–23 St to Jay St–MetroTech |
| Grand Central to Brooklyn Borough Hall | 5, Grand Central–42 St to Borough Hall |
| Court Square to Times Square | 7, Court Sq to Times Sq–42 St |
| Times Square to Brooklyn Borough Hall | 2, Times Sq–42 St to Borough Hall |
| Port Authority to NYU Tandon | A, 42 St–Port Authority to Jay St–MetroTech |

## Population and definitions

The original input grid covered November 1–18, 2026, every 15 minutes in New
York local time: morning 06:00–10:00, midday 11:00–14:00 and evening 16:00–20:00,
with end times excluded. This is 16 + 12 + 16 departures per corridor/day,
3,960 scheduled corridor checkpoints, and 270 daily corridor/period cells.
November 19 supplies boundary outcome evidence only; it contributes no
departure checkpoints, daily cells or aggregate performance exposure.
The subsequent calendar-only weekday view preserves all selected predictions
and pre-outcome event representatives; it excludes the five weekend dates
without inspecting outcomes. The selection is sealed separately in
`data/manifests/november-weekday-peak-selection.json`.
November 1 is the DST transition date; the grid is constructed using local
calendar datetimes rather than a fixed UTC offset. Midday is an analysis window,
not an empirically proven travel peak.

The whole-journey signed error is the screened final-prediction destination
arrival minus the raw MTA destination forecast for the exact selected train.
Access, waiting, riding and egress are composed coherently. All five fixed Stay
paths contain one train leg, so fixed egress cancels from the error, provided
the inferred boarding is catchable. A passenger who takes a different earlier
train on the same line is not represented by this exact-train estimand.

- The primary mean weights each scheduled departure checkpoint equally among
  checkpoints with a usable paired outcome.
- Mean positive error averages `max(error, 0)` over those same usable outcomes.
  It is distinct from mean error conditional on being late, which is retained
  separately in the machine-readable results.
- Repeated physical trains are valid repeated departure-time experiences, but
  are not independent observations. Distinct train-sequence counts are shown.
- A secondary event-balanced view selects the earliest input checkpoint per
  physical train sequence, date, period and forecast-duration band. Start-time
  aliases do not create new physical events. The selected representative is
  never replaced because its outcome is unknown. This view changes the
  population and does not replace the primary departure-time mean.
- Means retain the observed forecast-duration mix. Separate 0–15, 15–30,
  30–60 and 60+ minute strata expose that mix; pooled values are not a
  standardized common-horizon comparison.
- Missing predictions, missing labels, poor endpoint evidence and missed
  selected trains remain visible. Unknown values are never filled with zero.

Every necessary boarding-departure and alighting-arrival label must pass the
existing quality flags, exact normalized train/stop identity matching,
`confirmation_status="CONFIRMED"` with a finite confirmation receipt, and
absolute last-observed-to-proxy distance at most 180 seconds. These remain MTA
final-prediction proxies, not independent passenger measurements.

The frozen rows preserve normal, planned, disrupted, severe and unknown input
contexts as recorded by the existing archive classifier. Those classifier
values do not independently prove route-specific severe applicability. The
separate Stay/Switch service-problem evaluation owns that notice qualification.

## Reproduction

The chart renderer uses the separately declared analysis dependency set:

```sh
.venv/bin/python -m pip install -r data/requirements-analysis.txt
```

Prepare the November inputs at `data/manifests/november-2026-inputs.json`, then:

```sh
PYTHONPATH=.:algo .venv/bin/python data/scripts/analyze_november_peaks.py --prepare-inputs
PYTHONPATH=.:algo .venv/bin/python data/scripts/select_november_weekday_peaks.py
PYTHONPATH=.:algo .venv/bin/python data/scripts/analyze_november_weekday_peaks.py --verify-only
```

Input preparation reads snapshots and alerts, freezes all 3,960 forecasts and
event representatives, and records source/configuration/code hashes. It does
not open outcome labels. The input-only manifest remains stable. The separate
`data/manifests/november-2026.json` source manifest may progress from
`INPUTS_PREPARED` to `PREPARED` without changing frozen input artifacts.

After the full-October predictive model is sealed and all November labels are
prepared, score once:

```sh
PYTHONPATH=.:algo .venv/bin/python data/scripts/analyze_november_weekday_peaks.py
```

The scoring command requires the source's separate `daily_labels` mapping and
does not treat missing prepared files as statistical unknowns. It refuses to
overwrite a finished report. Predictions, exact outcomes and frozen input rows
remain under ignored `data/processed/november-peak-analysis/`. Compact reports,
CSV tables and the PNG chart live under
`data/reports/november-weekday-peak-delays*` and
`data/reports/november-weekday-peak-delay.png`. The inherited input freeze is
`data/manifests/november-peak-inputs-frozen.json`; final weekday selection and
scoring have additional separate manifests. The original all-date scorer is
preserved for reproducibility but is not used for the final weekday analysis.

The original October experiment, statistics and artifacts remain unchanged.
