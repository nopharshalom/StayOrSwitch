# Incremental Switch evidence with a denser checkpoint grid

This is a separate exploratory supplement to the frozen November 20
Google-defined three-corridor experiment. It addresses the user's request for
cases where unmodified MTA predictions lead to Stay, historical-profile
predictions lead to Switch, and historical records support a meaningful saving.
The original results are known and remain unchanged; this is not an untouched
test or a new model fit.

## Fixed scope before new outcome scoring

- Retain exactly the 49 corridor–incident pairs already confirmed by the
  original input-only official-notice review: Hayden LIC to NYU Tandon, Grand
  Central to Brooklyn Borough Hall, and Court Square to Times Square.
- Retain every original approved checkpoint and add all five-minute offsets
  from zero through 120 minutes after each incident's original applicable
  problem receipt. Keep the original relevant notice-receipt checkpoints.
- Use only October 25–31, 2026 decision times, with October 24 snapshot carry.
- Qualify new checkpoints only when the corridor, incident, line, direction,
  full selected segment, exposure-source type and exact notice-version set
  match a previously confirmed review. New or changed scopes remain excluded
  from this supplement; later notices never authorize earlier cutoffs.
- Preserve the current Google Stay path, all 22 usable candidate paths and the
  unresolved provider candidate, provider/research walking times, source feed
  ownership, training profile, freshness rules and prediction code.
- Shared-station 5-to-4 substitution is a valid Switch. Do not add an arbitrary
  transfer penalty. Historical selected-train catchability still applies.
- Freeze selected inputs, predictions, sources, code and scope before opening
  this supplement's outcome labels. Require all 322 original checkpoints to
  remain present with identical predictions.

## Comparisons and denominators

“Raw MTA says Stay” means the project's unchanged five-minute Switch rule
applied to unmodified MTA feed predictions. It is not an official MTA routing
recommendation.

The primary incremental comparison is the **raw-MTA mode's strict selected
journey versus the incident-profile mode's strict selected journey** at the
same historical cutoff. Do not substitute the unconditional fastest raw-MTA
candidate, or the model's independently selected Stay train, for the raw
policy's actual chosen Stay journey.

Report all checkpoints and one input-selected event representative separately.
For all pairs with a concrete Stay/Switch action in both modes, report model
gains, practical ties, losses and unknown outcomes. Also report the narrower
raw-Stay/model-Switch subset. Separately retain the model's Switch-versus-own-
Stay outcome metric for comparison with the original report.

Predicted Switch savings remain at least 300 seconds. Historical outcome
differences within ±180 seconds remain practical ties. Missing/unreliable
endpoints and missed selected trains retain explicit unknown complete gains.
Near-identical checkpoints, repeated train pairs and repeated incidents must
not be called independent successes.

After the full cohort is scored, illustrative positive examples may use the
earliest comparable meaningful gain per corridor–incident family, up to ten
families. These are outcome-selected illustrations; no such filtering changes
aggregate counts. If there are fewer qualifying independent examples, report
the shortage. Additional train/time examples from one incident must be labeled
as repetitions.

## Evidence limits and audits

Outcomes remain screened final MTA prediction proxies with declared walks,
not independently measured passenger trips. Check newly positive selected
endpoints for staleness, stop-removal timing and boarding slack. These checks
qualify the frozen result without silently changing the labels or cohort.
Large gains from waiting for one selected train do not automatically establish
gains against a passenger taking another earlier available train on the same
line. No adaptive Stay policy is introduced in this supplement.

The reproducible runner is `algo/scripts/evaluate_incremental_switch.py`:

```sh
.venv/bin/python algo/scripts/evaluate_incremental_switch.py --prepare-inputs
# Independently audit the new freeze before scoring.
.venv/bin/python algo/scripts/evaluate_incremental_switch.py --verify-only
.venv/bin/python algo/scripts/evaluate_incremental_switch.py
```

The preparation command refuses to overwrite prior prepared/frozen inputs.
Expanded local snapshots and scored records remain ignored; the report records
their paths and hashes. This supplement makes no new Google queries and does
not download or duplicate the original raw archives.
