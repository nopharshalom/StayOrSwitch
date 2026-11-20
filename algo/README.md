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

After [preparing the data and freezing profiles](../data/README.md):

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
