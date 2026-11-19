# Step 5 Experimental Protocol

This protocol is written before model fitting and final-test evaluation. The
machine-readable training configuration and frozen experiment manifest record
the exact settings used by a run. Step 5 evaluates train components; the live
journey comparator remains the Step 4 baseline until a later integration step.

## Questions and targets

Compare unchanged MTA predictions, a training-only grouped mean residual, and
small CatBoost residual regressors on the same eligible examples. Point
predictions target expected component times through squared-error training.
Report absolute error, tail error, and signed bias alongside RMSE.

- Arrival: inferred arrival minus the decision-time MTA arrival prediction.
- Departure: inferred departure minus the actual MTA departure prediction.
- Segment: inferred departure-to-arrival duration minus its MTA duration.

Arrival-as-departure predictions are excluded from the departure and segment
core models. Departure examples derived from multiple segments must be
deduplicated by service-qualified trip, boarding stop, and decision time.
Neither arrival residuals nor absolute arrival timestamps are departure labels.

The labels are final-prediction journal proxies from the same MTA source, not
independent physical observations. Passing an evaluation does not establish
passenger destination accuracy or realized route-choice savings.

## Data and feature separation

Data extraction, sampling, feature construction, and their tests live under
`data/`. Model fitting, prediction, and evaluation live under `algo/`.

Training uses November 2-8, validation November 9-11, and final testing November
12-15, 2026. Preserve source split ownership and label-availability exclusions.
Fit transformations, historical corrections, and support summaries only on the
training split. Use validation for model selection. Do not inspect final-test
performance until settings, support rules, and model artifacts are frozen.

The model-data manifest records a deterministic trip sample and one selected
snapshot per event and forecast-horizon bucket. Selection is independent of
outcome values. Retain eligible and excluded denominators; a selected row with
an unusable outcome must not be silently replaced with a convenient label.
Normalize weights within component events so repeated observations do not
create additional independent events. Report trips and dates as well as rows.

Core predictors must be reconstructible from one normalized live MTA snapshot
and the decision time. Use an explicit feature allowlist. Trip identifiers,
absolute calendar dates, future journal fields, outcome quality flags, and
later alerts cannot become predictors. Preserve unavailable fields as missing.
Normalize platform directions without interpreting GTFS direction 0 or 1 as
north or south.

`data/modeling/snapshot.py` constructs label-free component cases from the same
normalized MTA schema used by live integration and checks temporal availability,
freshness, true departure evidence, endpoint order, and forecast horizons. It
rejects known skipped or unavailable stops along the relevant component path.
Historical component features did not retain every intermediate stop's status,
so held-out model applicability is not a measured online applicability rate
under that additional guard. Skipped-service performance remains unvalidated.

Historical alert matching and receipt freshness differ from the current live
leg-level alert summary. Alert state is an evaluation grouping variable in the
core experiment, not a core predictor. Historical headways and rolling ETA
revisions also require additional live reconstruction. Any rolling-feature
ablation is validation-only research and is ineligible for live promotion until
equivalent buffering, sampling, and cold-start handling exist.

## Evaluation and adoption

Publish event-weighted MAE, RMSE, median and P90 absolute error, signed error
(outcome minus prediction), and coverage/fallback counts. Compare methods on
identical examples. Break results down by date, weekday/Saturday/Sunday,
line, horizon, and decision-time disruption information. Unknown alert state
is not evidence of normal service. Long planned weekend headways alone are not
an unexpected delay.

Validation contains weekdays only. Do not tune weekend-specific settings using
the final-test weekend. Two weekends and a few held-out dates cannot support
general weekend or incident-level reliability claims. Avoid row-level bootstrap
confidence intervals that treat repeated snapshots as independent observations.

Choose the compact model configuration on validation, then record model,
configuration, feature-code, data-manifest, and dependency fingerprints before
running final testing. Exact adoption and support rules belong in that frozen
configuration. Compare against both MTA and the simple historical correction;
report unexplained deterioration in key groups. Keep unsupported patterns,
invalid inputs, and insufficient coverage visible through baseline fallback or
unavailable outcomes. A successful training command does not authorize live
model activation, and a failed adoption gate is a valid experiment result.

Current extraction covers forecasts from zero to thirty minutes ahead and
excludes already-past predictions. Severe stalls may be missing. Report this
coverage gap before making disruption claims; targeted re-extraction is a
separate documented dataset revision, not a hidden test-set adjustment.

## Component composition checks

An offline composition uses corrected departure plus corrected riding duration.
It must not add the arrival residual again. Reject nonfinite, negative, or
temporally inconsistent component inputs. The model's nonnegative point-estimate
floor is configured before testing and reported when applied; it does not prove
that a train can be reached. Recheck platform readiness, train choice, and
downstream transfers after applying corrections, including cases where an
earlier prediction makes a previously catchable train unavailable. Synthetic
composition checks establish arithmetic and behavior only. Live integration
and the served evaluation API remain Step 6.
