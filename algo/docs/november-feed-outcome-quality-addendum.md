# Selected-outcome geographic sanity correction

This addendum was written after the first visible-feed replay was scored and
before its results were delivered. It is an outcome-quality correction on
already examined November records, not a newly blind evaluation. The initial
result, frozen inputs, exact producers and execution artifacts are preserved
under `algo/local/november-feed-replay/superseded/initial-v3/`, indexed by its
`preservation-manifest.json`. The corrected freeze references that record.

## Discovered source defect

A November 18 Port Authority to Tandon comparison appeared to save 18 minutes
47 seconds by switching from A to C. Its final C predictions implied only ten
seconds between 42 St-Port Authority and Jay St-MetroTech, about 7.2 kilometres
apart in a straight line. Inspection of the original normalized snapshots
found consecutive downstream stops advertised one second apart under the same
trip alias, followed by their joint disappearance. Endpoint freshness and
removal checks therefore passed despite an impossible travel-time sequence.
This was malformed source evidence, not a real measured journey or a route
arithmetic error. The source anomaly audit retains the exact records.

## Symmetric quality rule

For a selected leg with otherwise usable departure and arrival evidence,
calculate the great-circle distance between its archived official station
coordinates. Reject the leg as outcome evidence if its implied straight-line
average exceeds **300 kilometres per hour**. This is an intentionally generous
screening ceiling, not a claim about subway operating speed. Ignoring track
curves, station stops and acceleration makes the bound permissive. It screens
obvious collapsed timelines without estimating or substituting ordinary ride
times. A legitimate short hop is assessed by its own distance, not a blanket
minimum duration. Missing required coordinates remain explicit uncertainty.

Apply this rule only after the feed-based choice of a train. Keep candidate
views, current-feed ranking and the original endpoint values unchanged. Mark
the selected arrival unusable, retain the distance, duration, implied speed
and reason in the evidence, and stop that route's outcome reconstruction.
Do not choose another train to obtain a better-recorded result. This also
prevents an invalid arrival from setting transfer readiness.

The same screen applies to Stay, Switch, all decision policies, original and
boarding-safe advice, and every margin sensitivity. Preserve the original
predictions, cohort, walks, model, boarding margin, feed freshness and endpoint
age rules. No retraining or recommendation generation is authorized by this
correction. Earlier frozen studies are not rewritten; their comparison to the
new evaluator now includes this explicitly disclosed outcome screen.

## Validation and reporting

Bind the screening code, configuration and archived coordinate provenance in
the corrected freeze before rescoring. Test distant collapsed timelines,
valid adjacent-station rides, unchanged candidate selection and selected-bad-
outcome handling without fallback. Independently check every inferred leg and
the unchanged advice/cohort; report rejected records and their effects on both
positive and negative comparisons. A diagnostic scan at 100, 160, 200 and
300 kilometres per hour must remain a robustness check, not a search for a
favourable result.

Continue to call the remaining durations screened final-MTA prediction proxies
plus walking assumptions. This screen does not turn them into independently
observed passenger arrivals, and it does not resolve other missing selected
outcomes. Preserve the separate conditional-waiting evidence counts.
