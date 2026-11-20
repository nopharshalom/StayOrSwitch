# October aggregate profile bundles

`october-2026-profiles-train.json.gz` is a small, self-contained aggregate
profile bundle for the app teammate. It is byte-identical to the development
profile frozen for the October evaluation. It contains no raw archives or
individual forecast/outcome rows.

Training dates are **October 1–17, 2026**, in America/New_York. Validation and
test use the following two complete weeks. Full-month descriptive statistics
are separate and must not replace this bundle in held-out predictions.

Load it from the repository root:

```python
from data.delay_profiles import ProfileEstimator

profiles = ProfileEstimator("data/artifacts/october-2026-profiles-train.json.gz")
```

Pass the estimator to the supplied-route comparator described in
[the integration guide](../../algo/docs/severe-comparison.md). Its local runner
accepts the same path with `--profiles`. The bundle manifest records its byte
hash, internal content seal and training/protocol provenance.

This version uses historical means and distributions with explicit fallback
levels. Independent support is required per component group; counts are not
calibrated confidence probabilities. Severe-specific support is sparse in this
development window: only the A-line A27S to A41S segment has groups meeting both
the 20-event and three-severe-incident gates. Other severe contexts can fall back
to time profiles, with `incident_supported=false` and an explicit reason.
The caller should expose that limitation with the recommendation.

## Full-month descriptive history

`october-2026-profiles-month-descriptive.json.gz` is a byte-identical copy of
the completed October 1–31 descriptive profile. It contains 33,154 aggregate
groups, including weekday/Saturday/Sunday, time period and forecast horizon.
Its companion manifest records the source manifest, byte hash and content seal.
It contains no raw forecast rows or individual outcomes.

Use it to display historical means, distributions and support, following the
[readable tables](../reports/profiles-horizon-notes.md). Read it as gzip JSON;
`fit_split` is `month_descriptive`. `ProfileEstimator` deliberately rejects it
for prediction, because it includes validation and test outcomes. Load the
separate `train` bundle for the evaluated comparator. Endpoint errors are not
complete journey durations and must not be added twice to a route estimate.

These bundles are research algorithm artifacts. Read the complete source,
coverage and replay reports before making performance claims. Public v1 request
and response contracts remain separate from the richer diagnostic schema.
