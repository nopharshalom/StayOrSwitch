# Historical ETA Delay and Severe-Incident Decisions

The active implementation follows the [October plan](docs/october-implementation-plan.md).
The November component-model experiment and its data/results have been removed
at the user's request. Implementation status is recorded below and in the new
reports; no prior model accuracy or switching claim applies to this version.

## Current scope

- Full October 2026 history, with separate development, validation and test weeks.
- Historical ETA delay by route segment, direction, day type, time of day and prediction horizon.
- Official severe-incident context and meaningful savings, including seven route families.
- A common as-of cutoff and explicit unavailable outcomes for transfers and missing evidence.
- Historical statistics first; no CatBoost model is part of the new implementation.

## Implementation status

The plan, configuration, data pipeline, historical profiles, multi-route
comparator, evaluator and handoff instructions are implemented. The previous
data/model stack has been removed. The corrected frozen implementation passes
246 algorithm tests, 116 data tests and the retained 14-scenario contract validator.

All 64 required October/boundary archives and all 31 prepared days have been
verified. Full-month profiles and both held-out replays are complete. Monthly
description uses 871,210 eligible representative observations; predictive
evaluation uses only the frozen October 1–17 development profiles.
The [pre-evaluation identity correction](reports/october-protocol-revision.md)
documents the renewed protocol and unchanged decision/evaluation rules.

- [Historical means by time of day and forecast horizon](../data/reports/profiles-horizon-notes.md)
- [Complete monthly profile report](../data/reports/profiles.md)
- [Validation replay: October 18–24](reports/october-validation.md)
- [Final test replay: October 25–31](reports/october-test.md)

All 11 variants across seven route families were retained. The final test has
128 predeclared checkpoints from six incident families, but zero selected Stay
references with definite applicable severe exposure. There are therefore zero
strict Switch decisions and no validated severe-Switch success rate. Of the
14 incident-profile timing-only Switch diagnostics, four have comparable
outcomes: two meaningful gains, one practical tie and one meaningful loss;
ten remain unknown. These diagnostics are not formal incident advice.

Severe-specific training support meets the event and incident gates in only
eight broad A-line groups. Other severe contexts disclose fallback to time
profiles. All outcomes remain screened final MTA prediction proxies.

## Supplemental affected-route Stay replay

The user's follow-up asks about a commuter whose intended route is actually
affected, rather than already taking the fastest MTA route. The
[supplemental experiment](reports/affected-stay-context.md) holds the original
predictor, selected trains and thresholds fixed and changes only the Stay
reference. Official route/direction wording qualifies 150 route/checkpoint pairs
across seven incident families before scoring. All 11 candidate variants remain.

Read the [validation supplement](reports/affected-stay-validation.md) and
[test supplement](reports/affected-stay-test.md), with separately labeled
[observable case illustrations](reports/affected-stay-illustrations.md). Results are post-hoc and
separate from the original benchmark; neither unknown outcomes nor missed
trains count as successful recommendations. A mixed-line/direction severity
limitation in the frozen classifier is explicitly documented and audited out
of this cohort, without changing the original predictor or reports.

With the original complete replay archives available locally, verify the
supplemental freeze and reproduce both splits:

```sh
.venv/bin/python algo/scripts/evaluate_affected_stay.py --freeze-only
.venv/bin/python algo/scripts/evaluate_affected_stay.py
```

These commands check the original code, configuration, profile, case archives
and text-review hashes. They do not refit profiles or generate new routes.

## Same-run delay test

Start with the [combined default-route findings](reports/default-route-delay-findings.md)
for the comparable route-level missed opportunity, a negative example, and the
stricter same-run study's outcome limitations. Changing trains within the same
Stay route is valid for a route comparison; it cannot establish delay of the
earlier selected train. The findings keep these two claims separate.

The [same-run forecast revision replay](reports/feed-revision-test.md) addresses
the user's latest scenario directly: the original fastest route's selected
service run remains catchable, but its absolute destination ETA moves later by
at least five minutes. It compares Court Square to Times Square via 7, E or F.
The October 25–31 fixed five-minute grid and four reassessment lags yield 8,064
attempted pairs, two qualifying pairs and two distinct service runs. One initial
lead is within the predeclared three-minute practical-tie boundary; the other
is just above it. These are exploratory examples, not a general success rate.

Inputs and representative runs are frozen before this experiment reads outcome
labels. Earlier exploration of the same test week is explicitly disclosed.
The unchanged five-minute Switch threshold applies, with `require_severe=False`
because this request includes ordinary delays. The report evaluates both actual
recommendations and forecast-selected alternatives, including negative and
unknown outcomes. Final MTA predictions are screened arrival proxies, not
independent passenger observations; street walking remains an authored assumption.

With the prepared local sources, reproduce this separate experiment using:

```sh
.venv/bin/python algo/scripts/evaluate_feed_revision.py --prepare-inputs
.venv/bin/python algo/scripts/evaluate_feed_revision.py --freeze-only
.venv/bin/python algo/scripts/evaluate_feed_revision.py
```

The published freeze rejects changed code or inputs rather than silently
replacing the selected cohort.

The separate [Grand Central to Borough Hall extension](reports/feed-revision-brooklyn-test.md)
reuses the already-declared four paths after the two Court Square outcomes
failed quality checks. Five qualifying pairs yield three distinct delayed
service runs. All modes recommend Stay; two complete comparisons show the
forecast-best alternatives would be 6.75 and 14.75 minutes slower for the
incident-profile mode, while one comparison remains unknown. This is a disclosed
coverage-driven post-hoc expansion, with the earlier unknown cases preserved.
Reproduce it with the same three commands using
`algo/scripts/evaluate_feed_revision_brooklyn.py` instead of the Court Square runner.

## Earlier pre-incident route comparison

The [pre-incident route comparison](reports/preincident-brooklyn-test.md)
fixes the originally fastest route before a problem, then compares alternatives
at a later common departure cutoff. Its
[clear-default subset](reports/preincident-brooklyn-clear-default.md) separates
initially decisive choices from near ties. The test uses Grand Central to
Borough Hall with four supplied paths; 4/5 and 2/3 are each treated as compatible
same-corridor services, rather than artificial competing Stay/Switch routes.
These are authored research candidates, not historical Google itineraries.

This request includes ordinary delays, so this experiment explicitly calls the
existing comparator with `require_severe=False`. It preserves the original
predictor, training profile and five-minute Switch margin. Case selection and
official direction/scope checks were fixed before outcome scoring. The separate
[Court Sq to Times Square search](reports/preincident-test.md) retains its zero
qualified-case result instead of manufacturing a successful example.

All compared options include walking. The
[supplemental raw-input pipeline](../data/docs/preincident-inputs.md) preserves
trains that are usable at the new boarding stations even when the old pilot
origin no longer appears in their future stops. New exact segments can use the
frozen route-level statistical fallback; they do not necessarily receive zero
correction. Returned support levels identify which fallback was used.

The report compares Stay with the forecast-best alternative even when the
algorithm says Stay, and keeps hindsight-best alternatives separate. It exposes
missed opportunities as well as harmful recommendations and unknown outcomes.
However, all selected baseline/reassessment train sequences differ. The
[raw same-train audit](reports/preincident-brooklyn-headway-audit.json) shows that
the positive October 26 counterfactual's longer remaining duration came from a
later departure selecting the next train, whose forecast actually improved.
It therefore does not establish that the originally selected train became
delayed. Keep this exploratory route comparison distinct from a same-train
forecast-revision test.

## Algorithm handoff

Use [the comparator and integration instructions](docs/severe-comparison.md)
for the three modes: unmodified MTA, time-conditioned corrections, and
incident-conditioned corrections. The caller supplies candidate routes and an
explicit current route. Outputs preserve selected trains, historical support,
estimated savings, unavailable alternatives, and separate formal versus
conditional timing advice. The latter is not a product recommendation.

The [versioned aggregate profile bundles](../data/artifacts/README.md) let the
teammate run inference without rebuilding historical data. The inference bundle
preserves the exact frozen development statistics; neither bundle contains raw
data or individual outcome rows.
The separate monthly bundle is for descriptive history, not held-out inference.

The original benchmark commands below reproduce the published experiment at
commit `8752333`, with its matching local source artifacts. Its protocol seals
the entire algorithm module inventory. Later supplemental modules therefore
cause the original freeze check to reject the current checkout even though
the original predictor files remain unchanged. Use that published revision for
the original benchmark, and the separate runners for subsequent experiments;
do not overwrite a published freeze to bypass the check.

At the original revision, after [preparing the data and freezing profiles](../data/README.md):

```sh
.venv/bin/python algo/scripts/evaluate_october.py --freeze-only
.venv/bin/python algo/scripts/evaluate_october.py --split validation
.venv/bin/python algo/scripts/evaluate_october.py --split test --allow-final-test
```

The explicit final-test flag opens the held-out week only after the immutable
code, profile, source, and case-selection checks pass. The primary Switch
threshold stays at five minutes; validation reports additional two- and
three-minute decision thresholds without changing the final-test rule.

## Retained integration foundation

- [Live provider and MTA ingestion](docs/live-integration.md)
- [Unmodified MTA journey comparator](docs/baseline.md)
- [API contract](docs/contract.md) and [OpenAPI](contracts/openapi.json)
- [Simulated client examples](examples/README.md)
- [Data workspace](../data/README.md)

These components remain reusable. The live provider supplies navigation routes;
our algorithm estimates and compares them. The app teammate owns UI and maps.
