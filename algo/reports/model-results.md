# Step 5 Component Model Results

The frozen experiment is complete. The segment-duration model passed the predeclared component gate. Arrival and departure models did not beat the simple historical correction on the primary metric, so their learned corrections are not adopted. The live Step 4 comparator remains unchanged.

All numbers below measure agreement with inferred MTA final-prediction labels, not independently observed physical arrivals or passenger journeys. No realized Stay/Switch savings were measured.

## Final-test primary results

Final-test dates: November 12–15, 2026. Values are event-weighted RMSE in seconds; smaller is better. The model column includes the frozen support fallback on the same cases as both references.

| Component | MTA | Historical mean | Learned model | Frozen gate |
|---|---:|---:|---:|---|
| Arrival | 251.25 | 224.48 | 227.78 | RETAIN_BASELINE |
| Departure | 213.22 | 182.88 | 184.50 | RETAIN_BASELINE |
| Segment | 123.66 | 121.51 | 116.11 | PROVISIONAL_COMPONENT_IMPROVEMENT |

Arrival and departure improve MAE relative to both references, but fail the predeclared RMSE gate against the historical correction. This distinction is preserved; the primary metric was not changed after testing. The segment result is provisional component evidence only, not permission to enable a live model.

## Error details

| Component | Method | MAE (s) | P90 absolute error (s) | Bias (s) |
|---|---|---:|---:|---:|
| Arrival | mta | 121.05 | 258.00 | 87.23 |
| Arrival | history | 97.66 | 207.50 | 12.15 |
| Arrival | model | 96.04 | 205.00 | 18.58 |
| Departure | mta | 115.12 | 245.00 | 86.29 |
| Departure | history | 87.73 | 189.06 | 9.75 |
| Departure | model | 86.13 | 187.09 | 15.04 |
| Segment | mta | 54.83 | 130.00 | 13.68 |
| Segment | history | 53.77 | 124.04 | 6.80 |
| Segment | model | 46.91 | 109.47 | 4.79 |

Positive bias means the inferred outcome occurred later than predicted. Reported model error includes unsupported-context fallback. The JSON additionally reports an ungated model diagnostic (`raw_model`), with the same zero-second lower bound. Those extrapolated predictions are not the frozen adoption candidate; the support policy was not relaxed after observing test results.

## Sample and support coverage

The model-data build selected 25% of service-qualified trips by deterministic hash, then one snapshot per event/horizon bucket before label filtering. All nine views contain 447,506 retained rows: 226,572 for training, 109,699 for validation, and 111,235 for final testing. These are sampled component observations, not 447,506 independent journeys.

| Component | Training rows | Validation rows | Test rows | Test events | Test trips | Applied test rows | Fallback rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| Arrival | 99,393 | 47,962 | 49,196 | 18,118 | 5,985 | 46,685 | 2,511 |
| Departure | 63,585 | 30,866 | 31,016 | 12,176 | 4,761 | 29,526 | 1,490 |
| Segment | 63,594 | 30,871 | 31,023 | 12,179 | 4,761 | 30,574 | 449 |

Every retained component event contributes total weight one. Historical model applicability is not measured online coverage: the snapshot adapter additionally checks known skipped/unavailable intermediate stops and source freshness. Distinct event counts can overlap across context groups when an event has multiple prediction snapshots.

## Weekday and weekend results

| Component | Decision day type | Dates | Events | MTA RMSE (s) | Historical RMSE (s) | Model RMSE (s) |
|---|---|---:|---:|---:|---:|---:|
| Arrival | SATURDAY | 1 | 3,262 | 208.08 | 166.13 | 170.32 |
| Arrival | SUNDAY | 1 | 3,124 | 399.85 | 369.46 | 378.62 |
| Arrival | WEEKDAY | 2 | 11,732 | 207.08 | 183.84 | 184.09 |
| Departure | SATURDAY | 1 | 2,134 | 196.23 | 154.19 | 154.59 |
| Departure | SUNDAY | 1 | 1,992 | 301.75 | 268.30 | 271.19 |
| Departure | WEEKDAY | 2 | 8,050 | 189.80 | 162.70 | 164.18 |
| Segment | SATURDAY | 1 | 2,133 | 109.49 | 106.18 | 94.35 |
| Segment | SUNDAY | 1 | 1,996 | 175.71 | 170.45 | 164.69 |
| Segment | WEEKDAY | 2 | 8,050 | 110.92 | 110.21 | 106.35 |

Validation contained weekdays only. Training and final testing each include only one Saturday and one Sunday. The larger Sunday errors are visible; this experiment cannot establish general weekend reliability or justify weekend-specific tuning against the final test.

## Development selection and ablations

| Component | Core depth 4 RMSE (s) | Core depth 6 RMSE (s) | Without clock depth 4 RMSE (s) | Selected |
|---|---:|---:|---:|---|
| Arrival | 194.63 | 193.78 | 195.34 | core_depth6 |
| Departure | 195.60 | 194.41 | 195.79 | core_depth6 |
| Segment | 98.93 | 99.03 | 99.40 | core_depth4 |

The arrival rolling-history research model achieved validation RMSE 194.40 s, versus 194.63 s for the same-depth snapshot model and 193.78 s for the selected snapshot model. The small same-depth difference did not beat the best snapshot candidate. Rolling research was excluded from selection and never evaluated on final-test labels; online buffering and cold-start parity are not implemented.

## Alert and revision evidence

`KNOWN_DISRUPTION` means an active applicable archived service alert; it is not independent proof of physical delay. Upcoming-only, possible, fresh-without-known-alert, and unknown states are separate. `REVISED` denotes at least one observed ETA change and does not necessarily mean postponement. Departure-only alert context is unavailable.

The final-test JSON contains route, date, horizon, alert, and revision breakdowns. Upcoming-only groups contain only 7 arrival events and 3 segment events, below the predeclared 50-event group gate; those cases remain reported as insufficient. Unknown-alert cases remain in every overall denominator.

## Frozen execution and limitations

- Training completed in 87.4 seconds on this local run using four CPU threads.
- Final-test evaluation completed in 8.8 seconds.
- Frozen timestamp: 2026-11-19T22:24:56.051217Z.
- Frozen file SHA-256: `2859d88705fbc338ed21f37843b275e228a9c2c51db75d8019177c2e82cde5e2`.
- No feature, model, support threshold, or adoption policy was changed after final-test access.
- No calibrated uncertainty interval or incident-level confidence claim is supplied.
- Already-past forecasts and horizons beyond thirty minutes were excluded upstream; severe stalls may be missing.
- These labels share the MTA prediction source; independent arrival and passenger outcome validation is still needed.
- No historical Google itinerary candidates or defensible full passenger journey outcomes were available.
- No live model was enabled and no evaluation API server was added.

## Reproduction and artifacts

- [Training protocol](../docs/model-protocol.md)
- [Training and inference instructions](../docs/model-training.md)
- [Data preparation manifest](../../data/manifests/model-data.json)
- [Validation results](model-validation.json)
- [Pre-test frozen manifest](model-frozen.json)
- [Final-test results](model-test.json)

Model binaries, train-only support summaries, and the original frozen manifest are local under `algo/models/pilot-v1/`; they are ignored by Git and are fingerprinted in the public frozen manifest. The source and configuration reproduce the experiment.
