# Evaluation Criteria

Status: General evidence principles retained for the [October implementation](october-implementation-plan.md). Its temporal protocol and practical-savings thresholds supersede earlier experiment settings. Simulated API fixtures validate integration behavior only.

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

## October evaluation protocol

- Use October1–17 for development, October18–24 for validation and October25–31 for final testing, in America/New_York. Descriptive full-month profiles are separate from development-only predictive profiles.
- Keep exact train and incident groups separated across boundaries; verify source receipt availability and purge boundary outcomes that cannot support a frozen development fit.
- Use only information available by each decision cutoff. Later alert severity, outcome labels and future feeds cannot choose a train or make a connection catchable.
- Report weekday, Saturday, Sunday and all configured time periods separately. Planned weekend headways are not unexpected ETA errors.
- Count independent incidents and train events alongside correlated checkpoints. Missing evidence is not normal service or a successful decision.

## Baselines and consistent comparisons

Compare unmodified MTA-based estimates, time-conditioned historical profiles, and incident-conditioned profiles on the same decision cases and candidate sets. Record any provider/schedule fallback and show results by estimation source. Preserve the route provider's original ETA as a separate comparator when it was actually captured at that time.

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

Later stages require measured data quality, published chronological splits, baseline/model results, and explicit coverage and limitations before any improvement claim. Use the approved initial October parameters: at least300seconds predicted Switch savings and +/-180seconds practical outcome ties. Report uncertainty and unknown results separately; do not invent calibrated confidence or an overall accuracy guarantee.
