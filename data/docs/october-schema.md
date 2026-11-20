# October archive schema

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
