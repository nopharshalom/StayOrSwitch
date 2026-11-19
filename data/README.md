# Data Sources and Historical Processing

Keep data source files, downloaders, historical processing code, data tests,
configuration, manifests, and quality reports in this directory. ETA estimation
and Stay/Switch comparison code belongs in `algo/`.

## Step 5 model inputs

[Model-training views](docs/model-data.md) derive arrival, departure, and riding
duration examples from the verified historical shards. Their source loading,
feature construction, deterministic sampling, and tests remain in `data/`.
Run `.venv/bin/python data/scripts/build_model_data.py` from the repository root.
The selected pilot sample has separate train, validation, and final-test files;
it does not treat millions of repeated snapshots as independent events.
The [model-data manifest](manifests/model-data.json) and
[preparation report](reports/model-data.json) record all nine views and the
447,506 usable sampled rows.

`modeling/snapshot.py` builds label-free inputs from one normalized MTA snapshot
using the same core feature transformation and explicit freshness, timing, and
departure-basis checks. It does not collect feeds or activate learned estimates
in the live comparator. Model commands and results belong in
[the algorithm package](../algo/README.md).

## Historical pilot

The accepted pilot covers Subway Data NYC archives for **2026-11-02 through
2026-11-15 inclusive**. Archive dates are New York calendar dates; trip service
dates and original collection timestamps are separate fields. The window was
expanded from one week to two on 2026-11-19.

- [Processing guide and limitations](docs/historical-pipeline.md)
- [Pilot stations, sampling, feeds, and date splits](config/pilot-history.json)
- [Source and derived artifact manifest](manifests/history-pilot.json)
- [Verified Python runtime and dependency versions](manifests/history-runtime.json)
- [Quality report](reports/history-pilot.md)
- [Machine-readable quality report](reports/history-pilot.json)

Use the repository's local Python environment, with the dependencies in
[requirements.txt](requirements.txt), which includes the shared live-data
decoder dependencies. Run these commands from the repository root:

```bash
# Verify a weekday and a weekend sample before the full run.
.venv/bin/python data/scripts/build_history.py --dates 2026-11-02,2026-11-07

# Download and process the full configured window.
.venv/bin/python data/scripts/build_history.py

# Reprocess verified local archives without downloading them again.
.venv/bin/python data/scripts/build_history.py --process-only

# Run synthetic archive, feature, label, and leakage checks.
PYTHONPATH=algo:data .venv/bin/python -m unittest discover -s data/tests
```

The pipeline streams compressed archives rather than extracting the full raw
history. Its station and forecast-horizon scope describes the training dataset;
it does not impose walking, transfer, detour, or route limits on the live app.
Actual coverage, exclusions, and artifact paths are recorded in the manifest and
quality report. Download dates and checksums support reproducibility; a local
checksum is not a publisher signature.

## Directory ownership and retention

| Path | Purpose | Git policy |
|---|---|---|
| `history/` | Archive parsing, as-of features, labels, and quality checks | Commit code |
| `modeling/` | Training views and shared offline/live feature construction | Commit code |
| `scripts/` | Reproducible data commands | Commit code |
| `tests/` | Synthetic data-processing regression tests | Commit code |
| `config/` | Explicit dataset scope and policies | Commit configuration |
| `docs/` | Data definitions, commands, and limitations | Commit documentation |
| `manifests/`, `reports/` | Source provenance and compact aggregate evidence | Commit small reports |
| `raw/subwaydata_nyc/` | Downloaded daily source archives and retrieval metadata | Local, ignored |
| `processed/history-pilot/` | Derived feature/label shards | Local, ignored |
| `processed/model-pilot/` | Sampled, event-weighted training/validation/test views | Local, ignored |
| `local/mta/` | Step 2 current static GTFS and as-of MTA snapshots | Local, ignored |

Large raw and processed datasets stay under `data/` locally. Publish paths,
sizes, checksums, and reproduction commands in Git rather than copying the
archives into the repository history. Do not commit API credentials.

## Interpretation and evaluation

Subway Data NYC CSV arrival times are inferred from the last MTA prediction.
They are **not independently observed physical arrivals**. Vehicle-derived
consistency checks share the MTA source and must not be presented as independent
ground truth. Preserve label method, quality flags, unavailable outcomes, and
source timestamps alongside each example.

Features may use only information available by their decision timestamp. Later
CSV outcomes and stopping-pattern changes belong to labels or quality metadata,
not input features. Keep every trip in one chronological split and prevent
outcomes crossing the split cutoff from entering training. Report weekdays,
Saturdays, and Sundays separately. Planned weekend headway differences are not
the same as unexpected prediction errors.

Historical MTA snapshots do not contain historical Google route ETAs or prove
which complete alternative journeys a provider would have offered. Current
static GTFS is useful for station identities, not historical route availability.
Full-journey replay requires date-appropriate service arrangements and defensible
candidate and outcome evidence. See the [evaluation criteria](../algo/docs/evaluation.md).

## Live inputs

Official MTA source URLs are in [mta-sources.json](mta-sources.json). The runtime
uses Google-generated candidate routes and applicable live MTA observations;
Google payloads are handled in memory and are not archived as training labels.
See [live integration](../algo/docs/live-integration.md) and the
[baseline comparator](../algo/docs/baseline.md).

The teammate owns app UI and navigation. The overall sequence remains in the
[seven-step algorithm roadmap](../algo/README.md).
