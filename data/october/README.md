# October source preparation

This package prepares the October 2026 Subway Data NYC archive for delay profiles
and incident replay. It does not train a model or generate navigation routes.

From the repository root:

```sh
PYTHONPATH=.:algo .venv/bin/python data/scripts/prepare_october.py --download-only
PYTHONPATH=.:algo .venv/bin/python data/scripts/prepare_october.py --process-only --dates 2026-10-04 --workers 1
PYTHONPATH=.:algo .venv/bin/python data/scripts/prepare_october.py --process-only --workers 4
```

The configuration is `data/config/october.json`. Acquisition includes 31 daily
realtime archives, 31 October CSV journals, and September 30 / November 1 CSV
journals for boundary outcomes. Raw archives and normalized artifacts remain
local under the ignored `data/raw/october/` and `data/processed/october/` paths.
The acquisition manifest, preparation manifest, and source report retain hashes,
sizes, source URLs, local paths, date coverage, and quality counts.

## Normalized observations

Each day produces `.snapshots.jsonl.gz`, `.alerts.jsonl.gz`, `.trips.json.gz`,
`.receipts.json.gz`, and `.source.json` files. The alert stream is an exact
projection of the dedicated alert-feed records in the complete snapshot stream.

Train snapshots normally use the first capture in each 60-second bucket.
Known malformed, conflicting, future-dated, unsupported, or stale captures, and
their first valid recovery, are also retained within the bucket. Every archived
train capture contributes to the receipt index. Every archived dedicated alert
capture is preserved. Train capture dates are verified against their New York
local archive dates, and collector timestamps remain explicit UTC instants.

Daily snapshot streams are chronological within each feed, **not globally
sorted**. Use `data.october.sources.read_snapshots(path)` to stream records.
Every configured-route train retains its descriptor, cancellation state,
timestamps, and identity aliases, including actual `FX` and `7X` variants. Before
normalization, a declared protobuf projection retains every configured endpoint
occurrence, each complete ordered path between configured leg endpoints, and
outside-path track changes. Unrelated stop updates are omitted; trains without
a configured path remain as metadata records. Intermediate skipped/no-data
stops and duplicate/reversed endpoints remain intact. Every source payload's
original hash is preserved alongside explicit projection counts and a separate
projected-payload hash. Raw archives remain complete.

## Separate outcome labels

`labels.json.gz` and daily `.labels.json.gz` files contain endpoint outcomes keyed
by the normalized train ID. Use `data.october.sources.read_labels(path)` to read a
label map. Labels never appear inside decision-time snapshots.

The publisher's CSV identifier uses UTC midnight of the encoded service date,
plus the raw trip-ID offset. It is an opaque join key, not a local departure
timestamp. A stable `canonical_event_trip_id` unifies start-time-only aliases for
physical-event deduplication and split purging while retaining each normalized
ID for exact snapshot lookup. Conflicting service, route, direction, unscheduled
run, and journal identities remain unusable.

Arrival and departure have separate quality flags. Schedule changes, rewrites,
missing passage evidence, long disappearance gaps, and other ambiguous journal
records are retained with explicit exclusions. `confirmed_at` is the first
archived same-feed collector receipt whose source time is **strictly after** the
journal's disappearance timestamp. An unavailable confirmation remains null.

These labels are quality-screened final MTA prediction proxies, not independently
verified physical arrivals. Fitting code must require confirmation before its
fitting cutoff. The label writer processes service-date groups and maintains a
bounded cache of daily receipt indexes; complete trip endpoint unions are kept
across observation days.

## Reproducibility

Downloads and daily outputs support verified cache reuse. Archive traversal,
member types, sizes, download hosts, and payload parsing are checked. Preparation
fails if source code or configuration changes during a run. `PREPARED` is emitted
only when all configured October dates have completed; subset runs are explicitly
marked `SMOKE_PREPARED`.

Run the focused boundary checks with:

```sh
PYTHONPATH=.:algo .venv/bin/python -m unittest data.tests.test_october_sources data.tests.test_october_labels
```
