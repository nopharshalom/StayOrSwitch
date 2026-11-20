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
data/model stack has been removed. The frozen implementation passes 245 algorithm
tests, 111 data tests and the retained 14-scenario contract validator.

All 64 required October/boundary archives have been acquired and verified.
Whole-month preparation is running; full profiles and held-out replay are pending.
Completed real-data results will be linked here only after verification.

## Algorithm handoff

Use [the comparator and integration instructions](docs/severe-comparison.md)
for the three modes: unmodified MTA, time-conditioned corrections, and
incident-conditioned corrections. The caller supplies candidate routes and an
explicit current route. Outputs preserve selected trains, historical support,
estimated savings, unavailable alternatives, and separate formal versus
conditional timing advice. The latter is not a product recommendation.

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
