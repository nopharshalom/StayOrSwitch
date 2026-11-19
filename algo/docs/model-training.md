# Component Model Training and Evaluation

Step 5 trains and evaluates historical residual models. It does not activate a
learned model in the live journey comparator or start an API server. The
[experimental protocol](model-protocol.md) and
[machine-readable configuration](../config/model-training.json) define the
experiment before final-test access.

## Responsibilities and commands

Data extraction, sampling, feature construction, and the snapshot-to-feature
adapter live under `data/modeling/`. Model fitting, inference, composition checks,
and evaluation live under `algo/stayorswitch/model_training/`.

From the repository root:

```sh
.venv/bin/python -m pip install -r algo/requirements-model.txt
.venv/bin/python data/scripts/build_model_data.py
.venv/bin/python algo/scripts/train_models.py
.venv/bin/python algo/scripts/evaluate_models.py
```

The data command verifies the prepared two-week source dataset and writes
deterministic chronological views. It samples 25% of service-qualified trips by
a stable hash and chooses one snapshot per component event and horizon bucket
before filtering unusable labels. It never replaces a selected unusable label
with another convenient observation. Each retained event has total weight one.
The manifest records full-source and sample denominators; model results describe
the retained sample, not all source snapshots or passenger requests.

The training command opens only training and validation views. It fits all
training-dependent statistics there, selects a core model on validation, and
writes a frozen manifest before the final-test command can run. Existing frozen
experiments cannot be overwritten by training. An evaluation command with an
unchanged existing final-test report returns that report without reopening test
labels. A different model or data revision requires a new experiment version;
reusing the known test dates cannot establish an untouched new test result.

## Targets and evidence

| Target | Baseline component | Residual label |
|---|---|---|
| Arrival | MTA arrival minus decision time | Inferred arrival minus MTA arrival |
| Departure | MTA departure minus decision time | Inferred departure minus MTA departure |
| Segment | MTA destination arrival minus origin departure | Inferred departure-to-arrival duration minus MTA duration |

Departure and segment training require an actual departure prediction. An
arrival-as-departure proxy is not silently treated as equivalent. Departure rows
derived from segment examples inherit conservative quality checks for both
segment endpoints and therefore do not represent every possible boarding event.

Labels are final-prediction journal proxies derived from the same MTA source.
Metrics measure agreement with those proxies. They do not establish physical
arrival accuracy, passenger destination accuracy, or realized Stay/Switch
savings. Current extraction covers forecasts zero to thirty minutes ahead;
already-past forecasts and potentially severe stalls are outside this dataset.

## Models and fixed selection

Every comparison uses the same held-out cases and event-balanced weights:

1. Unchanged MTA component predictions.
2. A training-only hierarchical mean residual. Detailed operating-pattern,
   day-type, two-hour clock, and horizon groups back off to route/day/horizon,
   route/horizon, horizon, and the global training mean. A non-global group
   requires at least 20 distinct training events.
3. CatBoost residual regression with squared-error training. Core candidates
   use depth 4 or 6, and a depth-4 clock-feature ablation removes the circular
   time-of-day inputs while retaining day type. Each has up to 350 iterations,
   validation early stopping after 40 rounds, learning rate 0.06, regularization
   5, random seed 5900, and four CPU threads.

Core selection minimizes validation event-weighted RMSE after applying the
frozen operating-support gate. Exact ties retain the first configured
candidate. No final-test score participates in candidate selection.

Arrival also has one depth-4 research experiment using the four archived
rolling-update features. It is evaluated only on validation and cannot become
the selected model or run on the final test. Equivalent online buffering,
sampling, and cold-start behavior remain future work.

Core inputs are an explicit snapshot feature allowlist: route, feed, platform
direction, day type, station or segment identity, clock, source age, assignment
state, prediction horizons, and available stop counts/patterns. No raw trip ID,
absolute service date, future outcome, quality flag, or later alert is an input.
Historical alert summaries and revision groups are evaluation metadata only.
Missing numeric inputs remain missing rather than becoming zero.

## Support and fallback

The learned model requires at least 20 distinct training events supporting its
operating context. Arrival and departure support includes the observed approach
pattern through the target stop. Training admits suffixes of an observed
approach so normal train progress is supported, while an unseen detour or
reordered approach falls back. Segment support uses its exact observed
component pattern. Unsupported contexts and horizons use unchanged MTA values
and stay in metric denominators.

All methods use a zero-second lower bound for predicted durations/horizons. The
reported `raw_model` is a diagnostic prediction without the operating-support
gate but with the same lower bound; it is not the adoption candidate.

The reusable `ComponentPredictor` verifies frozen file hashes, Python/CatBoost/
NumPy versions, feature names/order/types, target semantics, baseline equality,
source freshness, departure basis, and pattern context. `predict_case` accepts a
case from `data.modeling.snapshot.build_snapshot_case` and needs no label fields.
Its results remain explicitly experimental and have no calibrated uncertainty.

The snapshot adapter additionally rejects known skipped or unavailable
intermediate stops. Historical views do not preserve every intermediate stop's
status, so historical support coverage is not a measurement of online
applicability. Neither helper changes Step 4's live comparator.

## Metrics, groups, and adoption

Reports include event-weighted MAE, RMSE, median/P90 absolute error, signed bias
(outcome minus prediction), paired changes against both baselines, and
model/fallback coverage. Counts include rows, component events, trips, dates,
and event-weight sums. Results are grouped by date, day type, route, horizon,
alert evidence, and observed ETA revision state. No row-level bootstrap or
unsupported confidence interval is presented.

`KNOWN_DISRUPTION` means an active scope-matched service alert; it is not proof
of physical delay. Upcoming-only and possible alerts are separate groups.
`FRESH_NO_KNOWN_DISRUPTION` does not prove normal operation, and
`UNKNOWN_ALERT_STATE` is not a zero-alert observation. Departure alert state is
unknown because historical segment alerts do not establish boarding-only
relevance. `REVISED` means at least one observed prediction change, not
necessarily repeated postponement.

Training is November 2-8, validation November 9-11, and final testing November
12-15, 2026. Validation has no weekend. The configuration is shared across day
types; weekend settings cannot be tuned against the final-test weekend. A
single training Saturday/Sunday and a single testing Saturday/Sunday do not
establish general weekend reliability.

The predeclared adoption gate requires lower overall event-weighted RMSE than
both unchanged MTA and the historical correction, with no RMSE increase against
either reference in day-type and alert-evidence groups containing at least 50
events. Smaller groups are reported as insufficient. Failure means retain the
baseline; passing means provisional component improvement, never automatic live
activation or a physical-performance claim. The strict policy is not relaxed
after final-test results become available.

## Artifacts and verification

- `data/manifests/model-data.json`: input fingerprints, selection, view hashes.
- `algo/reports/model-validation.json`: all development candidates and ablations.
- `algo/reports/model-frozen.json`: public copy of the pre-test frozen manifest.
- `algo/reports/model-test.json`: unchanged frozen-model final-test results.
- `algo/models/pilot-v1/`: ignored local models, historical summaries, support
  tables, development trip identities, and the original frozen manifest.

The frozen manifest records configuration, data-manifest, source-code,
dependency-lock, validation-report, and binary-model hashes. Training checks
source hashes both before and after fitting. Evaluation verifies the same
fingerprints before and after test access. Models and large intermediate files
remain local; the code, manifests, protocol, and reports are committed.

```sh
PYTHONPATH=.:algo:data PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m unittest discover -s algo/tests -p 'test_model*.py'
```

The checks cover chronological guards, event weighting, model support, feature
parity, frozen provenance, native-library fitting, and component composition.
Synthetic composition propagates corrected departure plus corrected riding
duration, rechecks catchability and transfers, and rejects arrival residual
double counting. It establishes arithmetic behavior only.
