# Shared October implementation interfaces

Configuration: `data/config/october.json`. Times in data records are Unix UTC
seconds; local grouping uses its named timezone. Dates are ISO local dates.
Modules import from repository root and `algo/` on PYTHONPATH.

## Source package: data.october

`sources.py`: safe download/verify functions and CSV/raw-snapshot iterators.
`prepare.py` and `data/scripts/prepare_october.py`: stream all configured dates.
Outputs in ignored `data/processed/october/`:

- `YYYY-MM-DD.snapshots.jsonl.gz`: normalized whole feed snapshots from the
  existing `stayorswitch.mta` parser, train groups sampled every 60 seconds and
  every distinct alert capture retained. Existing fetched/source timestamps
  stay ISO strings; add `captured_at` numeric seconds and archive provenance.
  Keep every configured-route train identity/status, including metadata-only
  missing-path records. Preserve every configured endpoint occurrence, complete
  original ordered slices for all configured riding legs, and track-change
  evidence; omit only unrelated stop updates. An unexpected feed/route pairing
  retains full stops. Full raw archives remain available and hashes identify
  original payloads; explicit projection metadata describes the derived view.
  Labels do not appear in snapshots. Preserve invalid latest captures as missing states.
- `labels.json.gz`: map normalized service-qualified trip `id` -> stop_id ->
  `{arrival_at, departure_at, available_at, arrival_usable, departure_usable,
  quality_flags, arrival_quality_flags, departure_quality_flags}`. Numeric
  times or null. Journal disappearance time is not receipt time; attach
  `confirmed_at` (first archived same-feed receipt with source timestamp strictly
  after the journal availability) when verified. Keep route/trip identity
  and source UID. All requested endpoint labels, including unavailable ones,
  stay in this map. Per-day labels may be used internally for bounded memory.
  Preserve normalized aliases, but use `canonical_event_trip_id` (feed, service
  date, actual route and raw trip ID) to deduplicate harmless start-time jitter.
  Conflicting core identities or directions remain unusable. Confirmation
  receipts use every raw capture, including captures omitted by train sampling.
- Acquisition/preparation manifest under `data/manifests/october.json` and
  coverage report under `data/reports/october-source.json`.

Expose `read_snapshots(path)` and `read_labels(path)` convenience functions.
Preparation can run acquisition separately from parsing and resume verified
daily outputs. A missing requested day is an explicit failure, not success.

## Profiles package: data.delay_profiles

Own incident classification/index, profile row construction and statistics,
and `data/scripts/build_delay_profiles.py`. Use the normalized snapshots and
separate labels; do not import deleted November modules.

Expose `IncidentIndex(snapshots, max_age_seconds=300)` with
`context_at(cutoff, route_id, stop_ids=None)`: dictionary with `state`
(`NORMAL`, `PLANNED`, `DISRUPTION`, `SEVERE`, `UNKNOWN`), `cause`,
`incident_ids`, `evidence_status` (`FRESH`, `LAST_OBSERVED`, `UNKNOWN`),
`first_observed_at`, `age_seconds`, `alerts`. Unknown is not normal; preserve
as-of versions, explicit recovery, shared impact and ambiguous scope.

Construct endpoint residual records for each supplied route-leg pair in config.
Departure correction adjusts the boarding endpoint; arrival correction adjusts
the alighting endpoint. Derive riding time by subtraction; do not also add a
ride correction. Historical ride residuals may be reported descriptively.
Predictions never read labels. Full-month descriptive profiles and frozen
training-only profiles are distinct. Validation/test labels never enter fit.
Cross-split physical trains and input-only unplanned DISRUPTION/SEVERE families
are purged from fitting. Planned-only and unknown-only families retain their
contexts without an independent-incident generalization claim.

Expose `ProfileEstimator(profile_path)` and
`estimate(target, route_id, from_stop_id, to_stop_id, cutoff, horizon_seconds,
context)` returning `{correction_seconds, supported, level, event_count,
incident_count, statistics, reason}`. `target` is `arrival` or `departure`.
Unsupported returns zero correction and an explicit fallback reason. Profile
rows deduplicate train/component events within horizon/time/context groups;
summary weights must not count repeated snapshots as independent trains.

Outputs: `data/processed/october/profiles-train.json.gz`,
`profiles-month.json.gz`, incident inventory, source-referenced profile rows,
and small reports/manifests. Save a reproducible training-profile seal before
the algorithm evaluator reads final-test outcomes. Freeze all relevant source,
profile, comparator and evaluator code before fitting or whole-month descriptive
outcomes are opened; subsequent artifacts reference and verify that protocol seal.

## Algorithm package: stayorswitch.severe

Accept normalized snapshots, explicit route templates, one cutoff, and a
ProfileEstimator. Modes: `mta`, `time_profile`, `incident_profile`.
`time_profile` queries ordinary/time groups; `incident_profile` queries actual
as-of incident context. Return per-route predictions and exact selected train
sequences, correction support, current-route decision, and separate strict vs
conditional evidence results. Apply the 300-second predicted Switch margin.
No formal Switch when severe applicability, timing, or required evidence is
unverified. The caller explicitly identifies the current route; replay alone
uses same-cutoff fastest MTA as reference. Out-of-scope alternatives remain
unavailable, not infeasible by assumption.

## Evaluator: algo/scripts/evaluate_october.py

Use the same candidate set/cutoff and exact selected train outcomes, validate
boarding and every transfer, and report both same-mode Switch gain and gain
versus original MTA reference. Unknown outcomes are not ties. Select severe
incident checkpoints without labels/model scores; report validation and test
separately, including all requested route-family coverage and abstentions.
Do not load final-test labels before the development profile is sealed.
