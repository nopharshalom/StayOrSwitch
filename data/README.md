# October 2026 Data Workspace

The active scope is **October 1–31, 2026**, America/New_York. Previous November
historical/model datasets, processing modules and reports have been removed.
Follow the [approved implementation plan](../algo/docs/october-implementation-plan.md),
[configuration](config/october.json), and [shared schema](docs/october-schema.md).

Data acquisition, normalized observations, screened outcome labels, incident
versions, time-conditioned statistics and data tests belong here. Algorithm
comparison and evaluation live under `algo/`. Raw and processed data remain
ignored local artifacts; small provenance manifests and reports are committed.

Development uses October 1–17, validation October 18–24, and test October 25–31.
Descriptive whole-month statistics must not be used to predict held-out cases.
Boundary September 30 / November 1 journals only resolve October labels.

Historical ETA error is final inferred arrival minus the MTA forecast available
at the query cutoff. Preserve separate signed/positive-only statistics, time
bands, horizons, day types and event support. Missing or expired forecasts,
changed service and unavailable labels remain visible in coverage counts.
Official alert text and versions distinguish severe unplanned incidents from
planned work and unknown evidence. Do not equate stale archive captures with
fresh live receipt or count repeated updates as independent incidents.

The source is [Subway Data NYC](https://subwaydata.nyc/), derived from official
MTA feeds. Final-prediction journal outcomes are proxies, not observed passenger
arrivals. Each downloaded archive and derived output must have provenance.

## Completed source preparation

All 31 October dates and 64 required archives are verified. The prepared source
contains 231,608 snapshots, including 8,410 service-alert captures, plus 2,162,769
raw train receipt records for outcome-confirmation timing. Alert capture counts
are not independent incident counts.

There are 196,024 endpoint label records, of which 167,216 have usable arrival
labels and 163,679 have usable departure labels. These counts include normalized
aliases; profile fitting deduplicates physical endpoint events separately.
See the [source quality report](reports/october-source.json),
[verification](reports/october-source-verification.json), and
[pre-evaluation identity correction](../algo/reports/october-protocol-revision.md).
The original normalization and corrected label producers have separate lineage.

## Reproduce the data preparation

Run from the repository root using the prepared Python environment:

```sh
.venv/bin/python data/scripts/prepare_october.py --workers 4
.venv/bin/python algo/scripts/evaluate_october.py --freeze-protocol-only
.venv/bin/python data/scripts/build_delay_profiles.py
```

Acquisition verifies cached archives and processing verifies daily fingerprints.
Use `--download-only` to acquire archives separately, or `--process-only` after
a complete acquisition. An explicitly partial check uses
`--dates 2026-10-04,2026-10-05`; profile smoke runs also require `--smoke`.
Partial runs do not satisfy the complete-month evaluation gate.

The protocol seal fixes code and configuration before fitting. The builder
seals development profiles before opening non-development descriptive outcomes.
Changing the experiment requires a new reviewed freeze and regenerated artifacts;
never use the descriptive month profile for held-out predictions.

Raw archives and large derived artifacts stay under ignored `data/raw/october/`
and `data/processed/october/`. Committed manifests identify them by path and
content hash; raw packages are not copied into documentation or Git.
