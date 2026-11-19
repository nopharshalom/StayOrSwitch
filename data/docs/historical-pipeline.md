# Historical Data Pipeline

Step 3 prepares scoped train-arrival and riding-segment examples. It does not
train a model or establish destination-ETA accuracy. All historical source
manifests, downloads, processing code, tests and derived data live under `data/`.
The shared MTA wire decoder is reused from the existing live integration.

## Reproduce the dataset

Run from the repository root using Python 3.9 or later:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r data/requirements.txt
.venv/bin/python data/scripts/build_history.py
```

The verified pilot used Python 3.9.6. `data/requirements.txt` reuses the exact
dependency lock from live integration. The observed processing runtime and lock
checksum are recorded in `data/manifests/history-runtime.json`.

The command downloads verified public archives, processes them by calendar day,
and writes progress as JSON lines. It does not need a Google API key. Downloads
use two workers and bounded retries; processing uses two day workers by default
(`--workers 1` through `--workers 4`) and does not extract daily archives.
One weekday's compressed raw archive is roughly 80 MB but expands to roughly
10 GB while streaming, so do not unpack the complete two-week window.

Useful modes:

```sh
.venv/bin/python data/scripts/build_history.py --download-only
.venv/bin/python data/scripts/build_history.py --process-only
.venv/bin/python data/scripts/build_history.py --process-only --dates 2026-11-02,2026-11-07
PYTHONPATH=algo:data .venv/bin/python -m unittest discover -s data/tests
```

`--process-only` performs no HTTP requests and requires valid local checksums.
The subset command is a smoke test, not a complete-window dataset. `--force`
rebuilds derived shards. Compatible shards are reused only when input, config,
code and output checksums agree. The manifest records whether all configured
dates were actually processed.

## Files and scope

| Location | Contents |
|---|---|
| `data/config/pilot-history.json` | Explicit dates, splits, station and route scope, sampling and forecast horizon |
| `data/history/` | Download, archive, causal feature, label, alert and quality-processing modules |
| `data/raw/subwaydata_nyc/` | Ignored original `.tar.xz` files and retrieval/checksum sidecars |
| `data/processed/history-pilot/` | Ignored per-calendar-day arrival/segment `.jsonl.gz` shards and detailed reports |
| `data/manifests/history-pilot.json` | Source URLs, retrieval timestamps, SHA-256 checksums, code/config fingerprints and outputs |
| `data/reports/history-pilot.json` | Machine-readable aggregate quality and coverage report |
| `data/reports/history-pilot.md` | Readable result summary |

The feature collection window is November 2–15, 2026, in America/New_York.
November 1 and 16 CSV journals provide boundary labels only; they do not add
training decision times. Raw archives contain calendar-day captures, which are
not necessarily the service date in each train descriptor.

The pilot includes ACE, BDFM, G, NQRW and numbered train feeds, 23 configured
route identifiers, and 66 platform stop IDs at 33 selected stations. Targets
cover LIC and Downtown Brooklyn and selected Manhattan transfer stations.
This is explicit initial training coverage, not exhaustive candidate-route
coverage and not a limit on the live comparator's walking or detour choices.
Current static station metadata is used only for station identity; historical
stopping patterns come from the historical snapshots.

Train processing retains the first unambiguous capture in each 60-second UTC
bucket. Revision features therefore describe sampled observations, not every
five-second source collection. Arrival and segment examples have a forecast
horizon of at most 1,800 seconds. These are dataset scope settings, not learned
confidence thresholds. Every archived alert capture is retained because an
alert can change within a train sampling bucket.

The retained horizon is **0–1,800 seconds**. Already-past MTA arrival predictions,
which can occur while a train is stalled, are outside this first dataset's
training coverage even when the containing feed is fresh. The shared
`outside_prediction_horizon` count includes these and forecasts beyond 30 minutes.
Step 5 must check this coverage, use an explicit fallback, or expand extraction
before claiming performance during severe stalls. Original archives are retained
for such targeted reprocessing.

## Causal features and timestamps

Each row separates `features`, `label`, and `provenance`. Features include the
forecast, previous sampled forecast changes, predicted headways, route, stop,
direction, current remaining stop sequence, vehicle state, time of day and
weekday/Saturday/Sunday. Historical CSV schedule rewrites and final stop times
never become decision-time inputs. Unknown values remain null.

The archive filename records the collector's UTC download timestamp. Current
upstream [Hoard source](https://github.com/jamespfennell/hoard/blob/fc5806759eca9713e5d92b975f4990e007790f4b/internal/tasks/download/download.go)
assigns that timestamp after reading the response body. This supports using it
as historical receipt evidence; the exact deployed archive collector version
and clock accuracy were not independently verified. Source feed timestamps and
our later archive download times are recorded separately.

Features reject future, stale, regressing or ambiguous snapshots and do not
merge full feeds. Remaining stop sequences distinguish changed service from
ordinary progress. A planned longer weekend headway is not automatically a
delay label. Forecast headways are gaps between predictions, not independently
observed departure frequency.

Historical service alerts are present in the actual protobuf archives, despite
the archive README's abbreviated list of train feeds. Because archives group
feeds rather than globally interleaving time, the pipeline first builds a compact
alert index and then joins it to derived rows using receipt times at or before
each decision. Selector fields apply conjunctively, and current versus already
announced upcoming alerts remain distinct. Deduplicated alert captures can have
long gaps without an outage. A last-observed alert older than 300 seconds remains
explicitly unverified; it does not establish a fresh current alert count or an
absence of disruptions.

## Labels and split integrity

The publisher explains that CSV arrival times are the final MTA predictions
retained after a stop disappears. Accordingly, arrival residuals compare the
decision-time prediction with a `CSV_LAST_PREDICTION_PROXY`. Segment labels use
CSV departure at the origin and arrival at the destination, both explicitly
inferred; missing departure is never replaced with zero. Segment features
preserve intervening stops from the snapshot. These are train components, not
complete passenger journeys or observed route-choice savings.

CSV trip UIDs are opaque join keys. Upstream journaling builds them from **UTC**
service-date midnight plus the encoded trip-ID offset, using integer seconds.
That timestamp can differ from physical departure and must not be used as a
travel-time feature. Joining verifies the raw trip ID and route as well as UID;
real 24-hour-offset alias collisions are excluded rather than guessed.

Labels retain missingness, duplicates, changed/re-written schedules, timestamp
order and source observation-gap flags. `eligible_for_training` identifies the
conservative proxy-label subset within each split. Step 5 must select both
`split == "train"` and `eligible_for_training == true` for fitting; eligibility
alone does not authorize using validation or test rows. Excluded examples remain in the output for
coverage accounting. CSV `marked_past` is a source time, not collection time.
The post-processing pass finds a sampled collector receipt whose source update
is strictly later than that marker, avoiding ambiguity between payloads sharing
an integer source timestamp. This uses a monotonic-source assumption and is not
direct confirmation of the particular stop disappearance. Missing receipt confirmation or confirmation across a
split boundary makes the row ineligible. This is a conservative receipt bound
under the publisher's journal method, not a CSV publication timestamp.

| Split | Service dates |
|---|---|
| Training | November 2–8 |
| Validation | November 9–11 |
| Final test | November 12–15 |

Decision dates must belong to the same split as their raw service-qualified trip.
Label horizons crossing a split boundary are excluded. Global integrity checks
count distinct trips and stop events, check split ownership and flag observed
cross-boundary identity continuity. A service-qualified ID alone does not prove
physical train independence when the feed changes identifiers. Remaining
unresolvable physical identity is a limitation, not a claim of perfect coverage.
There are only two weekends: the validation split has weekdays only. Model
selection must not repeatedly reuse the final test weekend. Report weekday,
Saturday and Sunday results separately in Step 5.

The report's `global_integrity`, `final_arrival_counts`, and
`final_segment_counts` are authoritative after all enrichment and continuity
purges. Per-day extraction diagnostics retain their stated scope so a later
global exclusion does not conceal earlier data-quality findings.

A sampled vehicle-status audit compares CSV endpoint proxies with separately
derived status-transition intervals. Both derive from the same MTA feed, so
agreement is a consistency check, not physical arrival accuracy. Sparse sampling
can miss short station stops. No independently observed arrivals were supplied.

## Source references

- [Subway Data NYC programmatic downloads](https://subwaydata.nyc/programmatic-access)
- [CSV schema and identity fields](https://subwaydata.nyc/data-schema)
- [Publisher's label derivation](https://subwaydata.nyc/how-it-works)
- [Upstream journal implementation](https://github.com/jamespfennell/gtfs/blob/main/journal/journal.go)
- [Upstream realtime date parsing](https://github.com/jamespfennell/gtfs/blob/main/realtime.go)
- [Upstream NYCT trip offset parsing](https://github.com/jamespfennell/gtfs/blob/main/extensions/nycttrips/nycttrips.go)

The current code audit establishes the implemented join convention and matches
sampled real records; it does not establish the historical publisher deployment
version. The source is credited as Subway Data NYC. No Google responses are
used as historical labels and no model has been trained in Step 3.

## Verified pilot run

The complete November 2–15 window finished on November 19, 2026. All 14 raw
archives and 16 CSV journals (including the two boundary companions) were
checksum-verified. The final global integrity audit passed across all 28 output
shards, with no duplicate example IDs, qualified-trip split conflicts, temporal
violations, or missing selected train feeds.

- Arrival examples: 8,355,779, including 7,623,040 with eligible proxy labels.
- Segment examples: 4,647,130, including 4,069,162 with eligible proxy labels.
- Distinct service-qualified trips across both artifact types: 102,594.
- Distinct arrival/segment events: 546,156; repeated prediction rows are not
  independent journeys or independent disruption incidents.
- Vehicle-status consistency comparisons: 20,506. These share the MTA source
  with the CSV and are not independent physical arrival observations.

Full-shard independent checks on November 2 and November 7 also matched their
reported counts, source joins, local day types, and receipt/split conditions.
These checks establish data-processing consistency, not prediction accuracy.
The machine-readable report and manifest contain the detailed counts, hashes,
scope and quality flags.
