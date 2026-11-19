# Evaluation Criteria

Status: Evaluation specification established in Step 1. Step 5's [component experiment results](../reports/model-results.md) now report agreement with inferred labels. Physical-arrival accuracy, realized savings, and operational service performance remain unestablished. Simulated API fixtures validate integration behavior only.

## Evaluation question and units

The primary question is whether delay-aware estimates improve destination arrival estimates and Stay/Switch decisions compared with the same supplied itineraries evaluated without learned corrections, especially during disruptions.

- A decision case contains one query time, the same not-yet-boarded user state, a preserved current itinerary, and the candidate alternatives supplied at that time.
- Evaluate train-arrival and segment predictions separately from complete destination ETA. Better first-train predictions do not establish better complete-journey predictions.
- Express durations, residuals, and savings in seconds. Preserve source and collection timestamps; use America/New_York service dates for grouping.
- Count unique trips, stop events, dates, and disruption events as well as prediction rows. Repeated snapshots are not independent passenger journeys.

## Labels and evidence

Classify outcomes by evidence before calculating metrics:

| Evidence | Permitted interpretation |
|---|---|
| Independently observed train or passenger arrival | Physical-arrival accuracy for the observed event and scope |
| Arrival inferred from GTFS-Realtime vehicle or stop observations | Accuracy relative to that explicitly documented proxy |
| Archive CSV arrival based on the last prediction | Agreement with the archive's inferred endpoint, not independent ground truth |
| Simulated itinerary or outcome | Contract, arithmetic, and scenario behavior only |

Record the label method, observation coverage, timing uncertainty, and exclusions. Do not pool these evidence classes into a single unqualified accuracy number. A label-validation sample should include ordinary service and disruptions; report disagreement and missing coverage, including difficult reroutes rather than silently dropping them.

## Chronological pilot evaluation

- The historical pilot window is 2026-11-02 through 2026-11-15 inclusive, expanded to two weeks on 2026-11-19. The planned service-date split is November 2-8 for training, November 9-11 for validation, and November 12-15 for final testing. Verify coverage and publish the actual split and boundary exclusions in the dataset manifest before training.
- Training dates precede validation dates, which precede final test dates. Keep each trip in one split, including cross-midnight observations; document boundary handling and any exclusion gap.
- Fit feature transformations and historical summaries using training data only. Select features, model settings, and uncertainty methods using validation data, then freeze them before final testing.
- Never construct an input using updates, future notices, inferred outcomes, or corrected data that were unavailable at the decision time. An old source timestamp alone does not prove the information had already been received.
- Report weekdays, Saturdays, and Sundays separately, including relevant stopping patterns and known service changes. The two-week window has only two weekends: the planned training and final-test ranges include weekends, but validation contains weekdays only. It cannot independently tune and test weekend behavior. Do not use the final-test weekend to choose model settings or describe two weekends as proof of general weekend performance.
- Distinguish planned service differences from prediction error. Longer normal weekend headways are not unexpected delays. Use only the headways and stopping patterns available at each decision time as features; later stop changes are outcomes or quality metadata. An unseen operating pattern must trigger documented fallback or insufficient-data behavior rather than an unsupported learned correction.
- If relevant cases are too sparse or labels are unreliable, report the limitation and request more data before drawing general conclusions. Do not replace a valid time split with random snapshot splitting to improve scores.

## Baselines and consistent comparisons

Compare unmodified MTA-based estimates, a simple historical correction, and the learned model on the same decision cases and candidate sets. Record any provider/schedule fallback and show results by estimation source. Preserve the route provider's original ETA as a separate comparator when it was actually captured at that time.

Do not add an MTA-trained residual directly to a provider's total ETA. Reconstruct the appropriate journey components and recheck catchable departures and transfers. If model corrections make a supplied itinerary infeasible, expose that outcome instead of continuing to score its original connection.

Current provider results are not evidence of historical candidate availability. Full-journey replay requires defensible date-specific itineraries, service arrangements, walking assumptions, and outcomes. Evaluate candidate coverage separately from prediction quality.

## Prediction and decision metrics

| Metric | Definition and reporting requirement |
|---|---|
| Signed ETA error | Outcome arrival minus predicted arrival; positive means arrival was later than predicted. Report bias and the distribution. |
| Absolute ETA error | Absolute signed error. Report mean, median, and a tail percentile with case counts and label class. |
| Prediction interval coverage | If calibrated intervals are supported, report their stated coverage level, observed coverage, and width on held-out data. Otherwise report uncertainty as unavailable. |
| Estimated savings | Estimated current-route duration minus estimated alternative duration at the same decision time. Positive means that alternative is predicted faster; this is not realized savings. |
| Outcome savings | Outcome current-route duration minus outcome alternative duration, only when comparable outcomes for both routes are available. Identify observed versus inferred evidence. |
| Selection regret | Selected-route outcome duration minus the minimum outcome duration among feasible supplied candidates, only when comparable candidate outcomes are available. Label inferred replay regret explicitly. |
| Decision behavior | Counts of Stay, Switch, and non-decision responses; disagreements with baselines; infeasible or missed connections; and switches with nonpositive outcome savings where evaluable. |

Only one itinerary is normally traveled by a passenger. Observing that trip alone cannot establish what would have happened on the alternatives. Do not report counterfactual outcome savings or regret as observed fact without the required evidence.

Break results down by disruption status known at decision time, repeated ETA revisions, prediction horizon, line/direction, time of day, weekday/weekend, and label quality. Publish the definitions of these groups before test evaluation. Report ordinary service as well as disruption cases. Account for dependence within trips, dates, and incidents when reporting uncertainty; row-level resampling can overstate precision.

## Coverage and operational checks

- Report all requested cases, including provider errors, absent alternatives, unmatched or ambiguous MTA trips, stale data, infeasible routes, unsupported model inputs, fallbacks, and cases without labels. Give denominators for each metric.
- An unavailable estimate is not zero minutes. No supplied alternative is not proof that no faster route exists. Do not count abstentions as correct recommendations or exclude them without showing coverage.
- Check request/response schemas, identifier references, units, time arithmetic, component totals, and preservation of the selected current itinerary.
- Check that all compared estimates share the same decision time and user state, future features are absent, and corrections do not double count delay.
- Exercise normal service, delay, reroute, no-alternative, missing-current-route, stale-feed, unmatched-trip, and missed-transfer cases using marked fixtures. Field names and response states must follow the API contract.
- Measure service latency and failure rates once a service exists; separate upstream-provider time from algorithm time. Delivery targets remain to be agreed with the app team.

## Completion and claims

Step 1 is complete when the contract, decision semantics, marked examples, and these evaluation criteria are internally consistent and usable for integration review. Fixture validation does not constitute model or live-service validation.

Later stages require measured data quality, published chronological splits, baseline/model results, and explicit coverage and limitations before any improvement claim. Do not invent a minimum time-saving threshold, confidence cutoff, latency target, or model-accuracy target. Rank by estimated complete-journey time under the confirmed objective; report uncertainty separately until another product policy is agreed.
