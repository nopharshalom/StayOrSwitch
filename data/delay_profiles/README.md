# Historical endpoint ETA profiles

This module converts archived, decision-time MTA forecasts into separately
sealed training profiles and full-month descriptive statistics. It does not
generate routes or train the previous tree model.

`IncidentIndex` reads alert snapshots and resolves the notice version visible at
a cutoff. Fresh, last-observed, planned, disrupted and unknown evidence remain
distinct. `ProfileEstimator` accepts only a sealed `fit_split="train"` artifact;
descriptive monthly artifacts are rejected for prediction.

```python
from data.delay_profiles import IncidentIndex, ProfileEstimator

context = incidents.context_at(cutoff, route_id, stop_ids=segment_stop_ids)
estimate = estimator.estimate(
    "arrival", route_id, boarding_stop_id, alighting_stop_id,
    cutoff, predicted_arrival - cutoff, context,
)
```

Use `context={"state": "TIME_ONLY"}` for a time-conditioned baseline. A response
reports the signed correction in seconds, support counts, fallback level,
statistics, requested/used context, and profile seal. Sparse severe groups fall
back explicitly to time profiles or zero correction; `incident_supported`
distinguishes these cases. The correction applies to the selected MTA endpoint,
not to an external provider's entire journey duration.

## Build

Prepare the daily source files first with the pipeline documented in
[`data/README.md`](../README.md). A smoke run may use only development dates:

```sh
.venv/bin/python data/scripts/build_delay_profiles.py --dates 2026-10-04 --smoke
```

The full October run requires the complete algorithm/data protocol freeze at
`algo/reports/october-protocol-frozen.json`. After that freeze is approved and
all daily sources are prepared, run:

```sh
.venv/bin/python data/scripts/build_delay_profiles.py
```

The builder verifies daily source projection hashes, reads input-only incident
and trip inventories, then opens development labels. It seals the training
profile before accessing validation/test labels for monthly description.
Protocol, source and code hashes are checked again during completion.

Artifacts under `data/processed/october/` include `profiles-train.json.gz`,
`profiles-month.json.gz`, `profile-observations.jsonl.gz`, and
`incidents.json.gz`. Small provenance manifests and readable reports live under
`data/manifests/` and `data/reports/`. Smoke artifacts have a `smoke-` prefix.
SQLite is temporary, bounds memory during deduplication, reuses training
membership pages for monthly fitting, and is removed on success.

## Interpretation and exclusions

- Errors are final MTA prediction proxies minus earlier MTA forecasts. They are
  not verified physical passenger arrivals.
- New York calendar day, day type, clock period and forecast horizon condition
  each endpoint/segment profile. Weekdays, Saturdays and Sundays stay separate
  until a declared broader fallback is needed.
- Mean signed error includes early arrivals. Mean positive error averages
  `max(error, 0)` across every usable event. Mean-if-late has a different
  denominator. Median, P80, P90 and probabilities above five/ten minutes remain
  available alongside the means.
- Physical identity uses feed, service date, actual route and encoded raw trip
  ID; start-time jitter does not produce additional independent events. Each
  aggregate deduplicates physical endpoint events again after pooling.
- At least 20 events support a predictive group. A severe group also requires
  three distinct definitely applicable severe publisher incident families;
  concurrent maintenance notices cannot satisfy that gate.
- Training labels need a confirmed source receipt before the training cutoff.
  Canonical trains crossing the split are purged. Crossing families that ever
  contain an unplanned disruption/severe version are purged through their
  effective presence/removal interval, including their earlier unknown rows.
  Planned-only/unknown-only notices retain their context; independent-incident
  generalization is not claimed for those categories.
- Missing, ambiguous and expired observations retain quality flags. Reports
  expose label coverage by time group and exclusions by service context, rather
  than silently removing difficult disruption examples.
