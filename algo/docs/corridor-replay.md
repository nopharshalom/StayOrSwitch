# Historical Corridor Delay Replay

This diagnostic asks whether unchanged model corrections can improve a route
choice for Hayden LIC Apartments to NYU Tandon. It does not retrain the models,
change the live comparator, or estimate an unbiased overall switching success
rate. The November 12-15 dates have already been inspected in Step 5; this is a
retrospective case study, not another untouched model test.

## Reference and supplied alternatives

The user selected the **fastest unmodified MTA estimate at the same decision
time** as the Stay reference. The baseline therefore chooses Stay by definition.
The question is whether the frozen learned correction changes that choice and
whether the chosen alternative has a faster inferred outcome.

The [experiment configuration](../../data/config/corridor-replay.json) supplies
two direct paths: F from Court Sq-23 St to Jay St-MetroTech, and G from Court Sq
to Hoyt-Schermerhorn followed by walking. Current provider routes were consulted
only to sanity-check the path templates and walking assumptions. They do not
establish historical provider candidates. Every replay must confirm the relevant
stations in order on a train actually present in the historical as-of feed.

Walking values are explicit experiment assumptions: F uses five minutes to the
platform and five minutes from the destination station; G uses four and twelve
minutes respectively. These include assumed station access/exit and are not
independently measured historical passenger times. Nearby entrances, closures,
walking-only trips, transfers, and all other possible subway paths are outside
this two-candidate comparison, not declared infeasible.

## Selecting delay cases before examining model recommendations

Search the existing historical component data for potential cases, then extract
the complete raw train snapshots available at the candidate decision cutoffs.
The initial search inherits the component dataset's zero-to-thirty-minute
forecast scope; complete raw snapshots can support longer candidate forecasts
in the ensuing replay, with learned corrections falling back outside scope.
Discovery covers 06:00 through 22:59 New York time on each configured day.
It uses G endpoint forecast errors and supplements F with origin-departure
errors because five minutes of access plus the F ride exceeds the initial
destination horizon. All discovered cutoffs enter raw baseline screening;
the initial route-local illustrative shortlist does not limit that pool.

A qualifying delay case has a baseline-selected train whose screened final
arrival proxy is at least 300 seconds later than the original MTA arrival
estimate, under the same walking assumptions. This threshold selects examples
for diagnosis; it is not a minimum savings threshold or a product preference.
The initial candidate pool, chronological spacing, event identities, eligibility
counts, and final selection must be recorded before model scoring. Do not select
cases using model switches, alternative outcome advantage, or realized-looking
savings. Keep failed switches, no-switch cases, and unavailable outcomes visible.
Detailed examples are the first six qualifying moments in time order, using
distinct baseline-selected train identities and at least 60 minutes between
examples. Preserve results for all qualifying moments separately; multiple
snapshots of one train are not independent delay incidents.

The selected endpoint sample is not a complete incident census. Large residuals
are not automatically invalid or automatically compelling: retain source-quality
and identity evidence and flag any unresolved continuity concern. Missing labels,
unverified boarding, absent candidate paths, and unavailable feeds must have
explicit counts rather than silently disappearing from a success-rate denominator.

## Predictions, composition, and recommendation eligibility

All prediction inputs use observations collected by one common decision cutoff.
Future CSV endpoints are only outcomes. Use the unchanged Step 5 model artifacts
and support rules. Compare:

1. Original MTA timing.
2. The segment model that passed the Step 5 component gate, with departure timing
   left at its original MTA prediction.
3. Frozen departure-plus-segment corrections as a separate research diagnostic;
   the departure model did not pass adoption and must not be presented as active.

For long legs, partition into consecutive supported selected-station segments
and add each nonoverlapping riding residual once to the original complete ride.
Keep intermediate dwell from the original MTA timing once. Never add an arrival
residual as well. Do not move the observation cutoff into the future to make
later segments appear supported. Report model applications and fallbacks.

Choose a train using predicted arrival after walking readiness, including
overtaking and any change to catchability from departure correction. No actual
outcome can select that train. Apply known service-conflict rules. The current
strict recommendation requires sufficiently fresh train and alert evidence;
archived alerts may be content-deduplicated and lack recent receipt evidence.
Report a conditional timing ranking separately from an eligible recommendation.
Missing alert freshness is not evidence that service was normal, and is not
evidence that a live collector would have had the same missing observation.

## Outcome comparison and sensitivity

Evaluate the exact service-qualified train selected by each prediction method
using quality-screened journal departure and arrival endpoints. Confirm that
the user could reach the platform before that inferred departure. If not, mark
the outcome unavailable rather than substituting a hindsight-optimal train.
The same rule applies to the Stay reference and every scored alternative.

Estimated switching savings compare the same prediction method's Stay and Switch
destination times. Inferred switching savings compare that method's selected
train on the Stay route with its selected train on the alternative route. The
method may change which train it would take while staying on the same route.
Separately report strategy gain against the original MTA-selected route and
train. Do not call an improvement over an inferior baseline train a successful
route switch when the model's own Stay train would have arrived sooner.
These are conditional train-record outcomes, not observed passenger savings.
They assume the filtered final ETA labels are sufficiently accurate for this
pilot. Validating that a different train would be faster does not prove the
user would have boarded it under unmodeled access conditions.

Vary each of the two paths' access and egress walking times independently by
-120, 0, and +120 seconds: 81 scenarios per selected case. Recompute catchability,
the MTA-fastest reference, and each model choice in every scenario. Report changes
to the reference separately so a walking-induced reference change is not
attributed to the model. Do not reselect the case set based on sensitivity results.

Data extraction and fixtures belong under `data/`; comparison and reports belong
under `algo/`. Large source observations remain ignored local artifacts with
recorded paths and hashes. The frozen Step 5 source and artifacts remain unchanged.

## Reproduction

From the repository root with the existing historical shards and frozen models:

```sh
.venv/bin/python data/scripts/scout_corridor_replay.py
.venv/bin/python data/scripts/prepare_corridor_replay.py
.venv/bin/python algo/scripts/replay_corridor.py --bundle data/processed/corridor-replay/replay-bundle.json.gz
```

The [data manifest](../../data/manifests/corridor-replay.json) records source
hashes and local artifact paths. The [baseline-only case selection](../reports/corridor-replay-case-selection.json)
is saved before model scoring. Read the [results](../reports/corridor-replay.md)
alongside the [compressed machine-readable comparisons](../reports/corridor-replay.json.gz).
