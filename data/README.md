# October Training and November Analysis Data

The current extension fits a separate model on **October 1–31, 2026** and
analyzes the **13 weekdays on November 2–6, 9–13, and 16–18, 2026**,
America/New_York, across the same five corridors. The
[weekday reporting addendum](../algo/docs/november-weekday-reporting.md) preserves
the original November 1–18 input grid; November 19 is boundary evidence only.
Follow the [new analysis plan](../algo/docs/november-five-corridor-plan.md) and
[November source guide](docs/november-2026-source.md). The original October
experiment and its artifacts remain preserved; the older, superseded November
tree-model experiment remains removed.

Data acquisition, normalized observations, screened outcome labels, incident
versions, time-conditioned statistics and data tests belong here. Algorithm
comparison and evaluation live under `algo/`. Raw and processed data remain
ignored local artifacts; small provenance manifests and reports are committed.

The original experiment uses October 1–17 for development, October 18–24 for
validation, and October 25–31 for testing. Its descriptive whole-month artifact
must not predict those held-out cases. The new full-October predictive artifact
is independently refitted and sealed for November analysis. November 2–15 had
prior project exposure, so November 16–18 is reported separately. September 30
and November 1 journals in the original October source remain boundary evidence.

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

## Full-October model and November weekdays

The current [feed-view adapter](docs/november-feed-route-archive-v3.md) exposes
each exact historical full-feed capture to the feed-following executor. Raw
forecasts and current membership are separated from the final endpoint records
used only after a train is selected. The adapter reuses the verified prior
archive, preserving all original data and label-quality rules.
An additional [selected-outcome quality screen](../algo/docs/november-feed-outcome-quality-addendum.md)
rejects physically impossible travel times using archived station coordinates.
It runs only after selection, retains the original records, and does not alter
candidate views or any earlier frozen study.

The separate [route-execution archive](docs/november-route-archive-v2.md)
supports the [boarding repair study](../algo/docs/november-repair-plan.md).
It retains timestamped path observations, strict endpoint evidence and unknown
earlier-train blockers, enabling the evaluator to continue along a fixed route
after a missed predicted train. Existing raw sources, labels, models and peak
statistics remain unchanged. The archive is an indexed reconstruction of
sampled MTA records, not independent physical movement measurements.

The separate [full-month training report](reports/full-october-fit.md) records
870,415 eligible October observations and 33,091 aggregate groups. The
[independent fit audit](manifests/full-october-fit-audit.json) verifies eligibility,
selected aggregate statistics, source separation, and the preserved experiment.

The [weekday peak report](reports/november-weekday-peak-delays.md) describes the
five fixed Stay paths over 13 November weekdays, with separate signed and
positive-only ETA errors and outcome coverage. Its
[daily table](reports/november-weekday-peak-delays-daily.csv) contains 195 cells;
the [daily heatmap](reports/november-weekday-peak-delay.png) shows positive-only
errors. Unknown and missed journeys are not zero delay. See
[the source guide](docs/november-2026-source.md) and
[peak reproduction guide](docs/november-peak-analysis.md) for commands.
There are 2,360 usable paired outcomes out of 2,860 scheduled checkpoints;
Court Square's midday 7 service has only 74 of 156. A low positive-only delay
does not imply a low absolute error. Raw-source audits linked from the report
explain that negative ETA errors primarily reflect overestimated waiting time
in that cell and verify the largest daily positive-error cells.

The separate [Stay/Switch results](../algo/reports/november-weekday-test.md) and
[interpretation](../algo/reports/november-weekday-interpretation.md) use service
problem checkpoints, not the daily peak grid. Their denominators must not be
combined with these descriptive delay statistics.

## Preserved October source preparation

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

## Preserved October experimental profiles

The month produces 1,095,007 representative observations, of which 871,210 are
eligible for full-month description, across 33,154 aggregate groups. The frozen
October 1–17 inference profile uses 469,466 eligible observations. Repeated
forecasts are deduplicated within each component/horizon/context group; these
counts are not distinct passenger trips or independent incidents.

Read the [time-of-day tables and horizon explanation](reports/profiles-horizon-notes.md)
and [complete profile report](reports/profiles.md). Weekdays, Saturdays and
Sundays remain separate. Severe support is sparse: only eight broad A-line
training groups pass both the independent-event and incident thresholds.
Other severe contexts retain explicit fallback instead of invented averages.

Small [versioned aggregate bundles](artifacts/README.md) are included for the
app teammate: one frozen inference profile and one descriptive whole-month
profile. Raw snapshots and individual outcome rows remain local. The
[final test report](../algo/reports/october-test.md) distinguishes conditional
timing comparisons from still-unvalidated severe-service recommendations.

## Reproduce the data preparation

The three-corridor experiment adds a
[current Google route and walking capture](docs/google-corridors.md) and a
[separate historical projection](docs/google-corridor-inputs.md) for newly needed
6, R and 7 endpoints. Both preserve prior sources and training profiles; current
provider durations are not historical outcome labels.

The five-corridor follow-up adds [two current Google paths](docs/incremental-extra-corridors.md)
and a [separate Times Square R endpoint projection](docs/incremental-extra-inputs.md).
The default paths are exact 2 for Times Square to Borough Hall and exact A for
Port Authority to NYU Tandon. The A/C station-access allowance is declared before
scoring and tested separately. Prior source files and training profiles remain unchanged.

The later pre-incident route experiment uses
[supplemental raw-feed projections and Bryant Park labels](docs/preincident-inputs.md)
so trains remain available after they pass the original pilot's boarding stops.
These separate test-week inputs use the existing archives and unchanged quality
rules. They do not replace the original source or refit historical profiles.

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
