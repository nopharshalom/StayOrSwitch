# Current Google route selection with historical service-problem replay

## User-approved question

On November 20, 2026, the user requested an experiment on three corridors using
existing October test data to assess whether switching during a service problem
can save time. The user explicitly clarified that Google's current recommended
route determines the **Stay path**, while historical records determine both
journeys' replay durations. Google's current number of minutes is contextual
information, never a substitute for a missing historical outcome.

This is a post-hoc exploratory experiment. The test week has been examined in
earlier studies; do not describe this as a new untouched generalization test.

## Corridors and current provider capture

1. Hayden LIC Apartments, 43-25 Hunter Street, Long Island City, to NYU Tandon,
   6 MetroTech Center, Brooklyn.
2. East 42nd Street and Lexington Avenue, Manhattan, to Brooklyn Borough Hall,
   209 Joralemon Street, Brooklyn.
3. Court Square Park, Long Island City, to West 42nd Street and Seventh Avenue,
   Manhattan.

Query the existing Google Routes integration for current subway journeys and
alternatives. Preserve request and receipt timestamps, the provider's route
labels, every returned candidate, walking steps and transit stop/line sequences.
Use the uniquely labeled `DEFAULT_ROUTE` as Stay. Missing, ambiguous or
unsupported defaults must remain explicit rather than silently being replaced
by a convenient route. Record the provider's current duration separately.
The capture shows that the provider's `routes.duration` and the duration from
the query clock to its final arrival plus egress can differ. Preserve both and
label the former as provider-reported duration; do not silently interpret it
as an immediate-departure door-to-door ETA.

Raw provider responses and normalized intermediate data remain ignored local
artifacts; commit derived provenance and route configuration without credentials.
Preserve the exact Google Stay line and stop sequence. Any compatible-service
pooling or same-station service substitution must be explicit in results.

## Candidate routes and historical inputs

Use the provider's usable alternatives plus the existing research route library
for these corridors. Freeze the full candidate set before outcome scoring.
Preserve unavailable candidates and their reasons; do not quietly delete
alternatives that cannot be evaluated. Deduplicate genuinely identical paths.

Provider walking estimates are held fixed for the historical replay, an explicit
assumption rather than a historical observation. Any supplemental research path
retains separately declared walking assumptions and endpoint reconciliation.
Evaluate material walking sensitivity without refitting the predictor: for
each primary case, vary one access, transfer or egress component of Stay or
its incident-profile forecast-best alternative by plus/minus 120 seconds,
skipping negative durations. Freeze these input-defined variants before labels;
report advice/selected-train changes and usable proxy gain ranges separately.

Replay October 25–31, 2026 in America/New_York. Use October 24 only to seed the
latest as-of snapshots at the boundary. Retain original ACE, G and alert
sources, use the separately verified pre-incident BDFM projection, and use the
new numbered/NQRW projection for Google's 6-to-R and 7-to-F paths. The latter
preserves earlier fields and adds the newly needed service/stop coverage.
Check every provider stop pair for source and label coverage; do not invent
intermediate stops, departures or walking times.

## Input-only service-problem selection

Select incident families first observed with an unplanned `DISRUPTION` or
`SEVERE` version during the test week and affecting the fixed Google Stay path.
Planned-only notices are excluded from the main service-problem cohort and
counted separately. Resolve unspecified work-train and maintenance notices in
the recorded text review rather than assuming they are unexpected faults.

Use the first problem receipt applicable to the exact Stay line and offsets
of 0, 5, 10, 15, 30, 60 and 120 minutes as fixed checkpoints, bounded by the test
week. Also include the exact receipt of each relevant problem version within
that two-hour window, deduplicating coincident times. This coverage rule was
expanded before selection was frozen or new outcomes were read: the input-only
notice audit found a 7 train incident whose severe wording arrived 103
minutes after its first ordinary-delay version. The window is not an exhaustive
sampling of every hour of a longer incident. Each checkpoint uses only feeds
and notice versions received by that time. Verify actual line, direction,
segment and wording before assigning exposure; later severe wording must not
be backdated to an earlier ordinary-delay version.

Build review candidates from the latest valid as-of alert capture's active
versions and raw line selectors, then manually qualify direction and segment.
Do not rely solely on the predictor's already-filtered incident context: the
input audit identified multi-clause notices where its frozen scope parser can
drop a legitimate both-direction delay. Preserve that predictor behavior for
this experiment and record differences between manual qualification and model
context; selection repair is not a hidden model fix.

Keep every confirmed checkpoint. The primary representative is the earliest
confirmed checkpoint with usable as-of Stay timing per corridor and incident.
If no such checkpoint exists, retain the earliest confirmed encounter as an
unknown-coverage case. Neither gains, recommendations nor later outcome
availability may select primary representatives. The earlier pre-incident
fastest-route and same-train-slip gates do not apply: this experiment explicitly
uses the current Google path, without claiming it was historically fastest.

Seal configuration, selected inputs, text qualification, producer code and the
unchanged training profile before reading the new cohort's outcome labels.

## Predictions and outcomes

Evaluate the same candidate set with raw MTA, time-profile and incident-profile
predictions. Preserve the current trained historical statistics and thresholds.
Use `require_severe=False` because the user asked about service problems broadly;
report ordinary and text-confirmed severe exposure separately.

All journeys start unboarded from the same origin at one historical cutoff.
Choose only catchable trains using that cutoff, including transfers. Score the
exact forecast-selected sequence; never replace a missed train using hindsight.
Count access, waiting, riding, transfer and egress time once.

- A model Switch requires at least 300 seconds of predicted savings.
- Replay savings are Stay's usable final duration minus the selected
  alternative's usable final duration. Differences within plus/minus 180 seconds
  are practical ties.
- Compare the forecast-best alternative even when the algorithm says Stay.
  Keep this counterfactual distinct from successful recommendations.
- Missing or unreliable endpoints and missed selected trains retain their
  reasons and unknown complete durations. Predictions cannot replace outcomes.
- Screened final MTA predictions are outcome proxies, not independently
  measured passenger arrival times.

## Required report

For each corridor, report the current Google Stay path/duration and capture
time, all compared paths and their walking provenance, selection/coverage
denominators, primary event results, supplementary checkpoint results and
exact model/proxy Stay-versus-alternative comparisons. Include negative and
unknown outcomes. Identify same-station service changes separately from
different transit paths when relevant.

Illustrations may use the earliest comparable checkpoint per incident after
scoring, but must be labeled outcome-availability-selected and must not replace
the input-selected cohort. An example saving time does not establish a general
Switch success rate or an improvement over Google/MTA across the city.
