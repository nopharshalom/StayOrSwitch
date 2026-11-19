# Model Training Views

Step 5 derives reproducible model input views from the already verified Step 3
historical shards. Source loading, feature transformation, sampling, target
construction, data tests, and dataset manifests live under `data/`. Model fitting,
prediction, and evaluation live under `algo/`.

The views contain inferred MTA prediction endpoints. They do not contain verified
physical train or passenger arrivals, historical Google route estimates, or
observed Stay/Switch savings.

## Reproduce the views

From the repository root, using the existing project Python environment:

```sh
.venv/bin/python data/scripts/build_model_data.py
PYTHONPATH=algo:data PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s data/tests -p test_model_data.py
```

This is local data preparation, not model fitting. It reads the checksummed
historical shards and does not need a Google credential or a network download.

| Location | Contents |
|---|---|
| `data/config/model-data.json` | Fixed sampling rule, source manifest, output paths, and feature version |
| `data/modeling/features.py` | Pure feature transformation shared with model prediction |
| `data/modeling/views.py` | Target construction, deterministic selection, weights, and view writing |
| `data/scripts/build_model_data.py` | Preparation entry point and source verification |
| `data/processed/model-pilot/{target}/{split}.jsonl.gz` | Ignored prepared examples for each target and split |
| `data/manifests/model-data.json` | Source, configuration, code, and output provenance |
| `data/reports/model-data.json` | Preparation counts and coverage evidence |

There are nine separate view files: three targets multiplied by three splits.
Each row separates `features` from event/trip/time metadata, baseline and label
seconds, target residual, sample weight, support key, and evaluation groups. The
feature transformer defines the predictor columns; passing an entire row to a
model would violate the input contract.

## Prediction targets

| Target | Baseline in seconds | Label in seconds | Residual |
|---|---|---|---|
| `arrival` | Current predicted arrival minus decision time | Inferred arrival minus decision time | Label minus baseline |
| `departure` | Current predicted departure minus decision time | Inferred departure minus decision time | Label minus baseline |
| `segment` | Current predicted destination arrival minus origin departure | Inferred destination arrival minus origin departure | Label minus baseline |

Departure examples are derived from the segment records, deduplicated by
service-qualified trip, origin stop, and decision time. Only records whose origin
prediction basis is `DEPARTURE_PREDICTION` are supported for departure and segment
models. An arrival substituted for departure is a distinct, unsupported input
basis in this version. An arrival residual must not be applied to departure time.

Segment-label eligibility is conservative: a departure example derived from a
segment also inherits that segment's endpoint and availability checks. Coverage
must therefore be described as the supported segment-derived departure subset,
not all departure predictions in the network.

## Features and online parity

The feature transformer uses an explicit allowlist. Trip identities, source CSV
UIDs, absolute prediction timestamps, exact dates, labels, later quality flags,
and future alert information are not model predictors. They may remain in
metadata for provenance, grouping, or evaluation. Only information available at
the decision timestamp is eligible as an input.

Core inputs are reproducible from a single live snapshot and its decision time:
route, feed, normalized direction, day type, cyclic time of day, feed/trip age,
assignment status, target station or segment pattern, forecast horizon, and
remaining stop count. Missing numeric features remain missing rather than zero.

Optional rolling arrival inputs, such as recent prediction revisions, require a
matching live history buffer. They are stored separately as `rolling_features`
research metadata and excluded from the default core predictors.
Missing history must not be encoded as zero revisions. Alert annotations are
evaluation metadata rather than core predictors in this version. Missing or
stale alert state must not be encoded as a fresh absence of disruptions. Existing
segment-scoped alert annotations cannot establish boarding-only departure scope,
so departure examples retain unknown alert context.

Operating support is based on route, direction, relevant stations, and observed
approach or segment stopping patterns. For station targets, training support
includes the suffixes of the observed approach to the target station. Normal
progress removes the beginning of that approach; it remains supported without
making a newly introduced stop or reordered path equivalent to the old pattern.

## Sampling and weights

The pilot selects 25% of service-qualified trips using the fixed sampling seed
`stayorswitch-step5-v1`, followed by at most one decision snapshot per component
event and horizon bucket: `[0, 300)`, `[300, 900)`, and `[900, 1800]` seconds.
Arrival/departure buckets use the corresponding station horizon; segment buckets
use the origin departure horizon. Selection is based on fixed hashes rather than
labels or residual magnitudes. The same rule applies to train, validation, and
test. This is a reproducible pilot sample, not a claim that all historical rows
were fitted or scored.

Snapshot selection occurs before label-eligibility filtering. If a selected
snapshot has no usable label, it is counted as excluded rather than replaced by
another snapshot with a more convenient outcome. Reports retain source-row,
eligible-row, selected, and excluded denominators.

Each selected event receives total weight one across its retained horizon rows.
Repeated snapshots therefore do not make a frequently observed stop event count
as many independent events. These weights do not establish independent physical
trains or disruption incidents.

## Chronological separation

| Split | Service dates | Purpose |
|---|---|---|
| `train` | November 2–8, 2026 | Fit model parameters and historical summaries |
| `validation` | November 9–11, 2026 | Select configuration and fallback policy |
| `test` | November 12–15, 2026 | Evaluate only after configuration freeze |

Trip ownership, decision dates, and label availability must remain consistent
with the Step 3 split. Files for the three splits are separate. Preparing and
counting test rows does not authorize using their targets for model selection.
The training command must not read final-test observations before freezing its
configuration.

Validation contains weekdays only. Saturday and Sunday results must be reported
separately, and final-test weekend results must not be reused to select settings.
Two weekends support a pilot, not general weekend-performance claims.

## Coverage and limitations

The historical extraction covers 33 pilot stations, five train feed groups,
60-second sampling, and predictions zero through 30 minutes ahead. Predictions
already in the past are outside the extracted scope; these can occur during
severe stalls. A model trained from these views cannot claim supported performance
for those missing cases. Such cases retain baseline or unavailable behavior
until separately extracted and evaluated.

Known disruption groups must use information available at decision time. Active
known alerts, known upcoming alerts only, and possible matches remain separate.
Unknown alert state is a separate group. A longer planned weekend headway does
not itself establish an unexpected delay.

The views preserve the source manifest and shard checksums, transformation code
fingerprints, configuration, output hashes, and row counts. A hash mismatch must
stop preparation rather than silently mixing source versions. Large generated
views stay in ignored `data/processed/`; small manifests and reports are versioned.

## Verified preparation run

The first complete preparation on November 19, 2026 verified and scanned all 28
source shards, containing 13,002,909 historical component rows. It completed in
331.5 seconds. The fixed sampling rule selected 501,183 target/event/horizon
candidates before label filtering and retained 447,506 usable rows. No conflicting
selected duplicates were found. The nine compressed output files total
71,932,373 bytes and remain local, ignored artifacts.

| Target | Training rows | Validation rows | Final-test rows |
|---|---:|---:|---:|
| Arrival | 99,393 | 47,962 | 49,196 |
| Departure | 63,585 | 30,866 | 31,016 |
| Segment | 63,594 | 30,871 | 31,023 |

These are preparation and eligibility counts, not prediction-performance results.
Departure views derive from the segment source, so adding source rows across all
three targets would double count that source. Exclusion-reason counts may overlap;
use selected and retained totals for the overall exclusion denominator. Per-split
event, trip, route, day-type, horizon and alert-context counts are recorded in the
[preparation report](../reports/model-data.json), with checksums in the
[model-data manifest](../manifests/model-data.json).
