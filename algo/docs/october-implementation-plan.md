# October Historical Delay and Severe-Incident Plan

Approved scope: replace the previous November component-model experiment and
two-route replay with this implementation. Use October 1–31, 2026 in
America/New_York. The user authorized removing the previous model/data source,
local artifacts, and results on November 19, 2026. Keep the reusable live MTA
and Google adapters, journey arithmetic, API contracts, and UI materials.

## Product output

For Hayden LIC Apartments, 43-25 Hunter Street, to NYU Tandon, 6 MetroTech Center,
report historical ETA underestimation by time and relevant riding segment.
When an applicable severe unplanned service problem exists, compare supplied
alternatives and recommend switching only for meaningful predicted savings.
The initial passenger has not boarded and leaves at the query time. External
providers generate routes; this project does not implement navigation.

## 1. Freeze definitions and temporal protocol

Signed ETA error is the screened final-prediction outcome minus the MTA ETA
available at the decision cutoff. Positive values mean MTA underestimated time.
Keep mean signed error, mean positive error over all cases, and mean error
conditional on being late distinct. MAE is not average delay. Report median,
P80/P90, probabilities of more than five and ten minutes of extra delay, and
independent event/date/incident support. Outcomes remain MTA-derived proxies.

| New York time | Analysis period |
|---|---|
| 00:00–06:00 | Overnight |
| 06:00–10:00 | Morning peak |
| 10:00–11:00 | Late morning |
| 11:00–14:00 | Midday |
| 14:00–16:00 | Afternoon |
| 16:00–20:00 | Evening peak |
| 20:00–24:00 | Late evening |

These are configurable analysis windows, not a claim that midday is empirically
a peak. Retain local clock information and separate weekdays, Saturdays, and
Sundays. Forecast horizons are 0–5, 5–15, 15–30, 30–60, and over 60 minutes.
Keep expired forecasts, absent/canceled trains, and unusable outcomes visible.
They cannot be treated as valid future departures or silently removed from
coverage counts. October uses the actual time zone, not a fixed November offset.

Development statistics: October 1–17. Validation: October 18–24. Final test:
October 25–31. Both evaluation windows include a complete Sunday–Saturday week.
Descriptive monthly profiles may use all October; prediction evaluation must
use development-only profiles frozen before final-test outcome scoring. Keep
cross-boundary physical trains and unplanned incident families out of development
fitting and retain purge counts. An input-only inventory identifies families
with any unplanned DISRUPTION or SEVERE version; if such a family crosses a
split, purge all associated development observations, including earlier unknown
or recovery versions. Planned-only and unknown-only notices remain explicit
contexts and can contribute time profiles; no independent-incident generalization
claim applies to those notices. This rule is frozen before fitting or scoring.
An event's future end time or later severity cannot be a
prediction feature. Collect September 30 and November 1 journals only for
boundary matching, not as additional decision dates.

Initial product parameters: predicted Switch savings at least 300 seconds;
outcome differences within +/-180 seconds count as practical ties. These are
different quantities. Report validation sensitivity at two, three, and five
minutes without selecting settings from final-test success. Initial minimum
support is 20 independent component events; severe-specific estimates also
require three distinct incident families. Sparse groups back off with the
actual scope and support disclosed. These are provisional support gates, not
calibrated confidence probabilities.

## 2. Replace historical inputs and build an incident inventory

Download and verify all 31 daily raw GTFS-Realtime archives and the required
CSV journals from Subway Data NYC. Stream compressed archives; record source
URLs, times, byte counts, and SHA256 hashes. Raw packages stay out of Git.
Use five train feed groups: ACE, BDFM, G, NQRW, and numbered trains, plus subway
alerts. Start from the already identified LIC, Manhattan-transfer, and Downtown
Brooklyn stations. Sampling frequency describes evidence resolution, not a
live route restriction. A small weekday/weekend smoke run precedes the month.

Normalize a compact view of the complete raw archive: retain all configured-route
trip identities and statuses, every requested endpoint occurrence, complete
ordered candidate-leg paths, and track-change evidence. Missing paths, repeated
endpoints, cancellations, vehicles, alerts and raw receipt evidence remain
visible. Preserve original payload hashes and explicit projection metadata;
unexpected feed/route pairings retain full stops. Require exact candidate,
profile-row and endpoint-inventory parity before adopting this optimization.

Join later journal outcomes to exact service-qualified train/stop identities.
The publisher's UTC-based opaque UID is not a local departure timestamp.
Preserve missing records, changed schedules, observation gaps, duplicates,
invalid endpoints, and unverified boarding. A changed schedule must not become
an invented normal journey. Maintain as-of observations separately from labels.

Preserve alert text, affected entities, source/receipt timestamps, and every
version. Automatically extract unplanned cause, severity, affected scope,
first-observed incident age, and recovery state, with explicit unknown cases.
Planned signal maintenance is not an unplanned signal failure. Group related
versions into incident families but preserve the time each version became
available. No later severe wording may be backdated across an entire incident.
Content-deduplicated archives do not prove a recent successful unchanged fetch;
strict freshness and conditional historical evidence remain separate.

## 3. Build time-conditioned historical profiles

Construct arrival and departure residuals. Derive each complete supplied-leg
riding duration from its corrected arrival minus corrected departure; do not
fit or add an overlapping riding correction in this version.
Group by route, endpoints/direction, weekday class, time period, forecast
horizon, and service context. Use one representative observation per event,
horizon, time band, and relevant context, with event weighting where needed.
Repeated feed snapshots do not create independent evidence.

Use hierarchical historical means/distributions first, without CatBoost or
another new learned regressor. Back off from detailed groups to wider time
groups, the same segment/direction, then route-level context when supported.
Do not silently merge unknown alerts into normal service or sparse severe
examples into an apparently well-supported severe estimate. Publish support
and fallback information alongside estimates. Ordinary profiles and severe
incident-conditioned profiles are separate artifacts.

## 4. Expand candidate comparisons

| Family | Research template, subject to historical service verification |
|---|---|
| F direct | Court Sq–23 St to Jay St–MetroTech |
| G direct | Court Sq to Hoyt–Schermerhorn, then walk |
| R direct | Walk to Queens Plaza, R to Jay St–MetroTech |
| E to A/C | Court Sq–23 St to 42 St–Port Authority, A/C to Jay St |
| 7 to 4/5 | Court Sq to Grand Central, 4/5 to Borough Hall |
| 7 to 2/3 | Court Sq to Times Sq, 2/3 to Borough Hall or Hoyt St |
| N/W to R | Queensboro Plaza to Herald Sq, R to Jay St–MetroTech |

Treat line variants as distinct alternatives when their services differ.
Live alternatives come from the provider; historical templates are explicitly
research-supplied, not historical Google outputs. Verify historical train stop
order, direction, access and transfer times, cancellation, and service changes.
Do not claim all templates run at all times. No arbitrary detour/transfer cap
is introduced. Walking assumptions must be explicit and tested for sensitivity. For validation
and test separately, use the first checkpoint of the first three chronological
incident families regardless of outcome availability; vary one walking component
at a time by +/-120 seconds and recompute reference, catchability and choices.
This bounded check is not an exhaustive joint walking-uncertainty analysis.

At one common information cutoff, process access, departure, riding, transfer,
and final walking in order. Recompute downstream catchability after correction.
Never use future feeds or hindsight-selected trains for a forecast. Apply each
component correction once, not an arrival correction plus the same departure
and riding correction. Score the exact forecast-selected train sequence;
missed connections or missing endpoints remain unknown.

## 5. Severe-incident decisions

Check that the severe incident affects the actual current journey. Estimate
remaining error not already incorporated in current MTA predictions using the
appropriate historical context. Retain current ETA revision evidence and
incident age for diagnostics and later refinement; do not claim they improve
prediction before validation. Compare every eligible supplied alternative.
Different route names do not prove independent infrastructure: F and G may
share a severe disruption, so assess R and numbered/Broadway alternatives too.

Use STAY, SWITCH, or UNDETERMINED with a reason, evidence freshness, support,
estimated savings, and comparison coverage. Severe text alone does not imply
that a line is physically impossible or that any alternative is better. A
severe-warning-only result is valid when timing or historical support is weak.
The existing API contract remains usable; supplementary diagnostics can carry
the richer profile and incident fields without breaking the teammate's client.

## 6. Evaluate and hand off

Freeze the candidate policy and choose incident checkpoints before evaluating
outcomes: first observed applicable severe notification and fixed five-minute
checkpoints, including escalation/recovery. Retain independent incident counts,
case counts, non-decisions, missing outcomes, and route-family coverage.
Do not choose only large realized delays or favorable Switch outcomes.

Compare unmodified MTA, time-conditioned historical corrections, and
time-plus-incident corrections on identical candidates and cutoffs. The replay
Stay reference is the fastest unmodified MTA candidate at that cutoff, as
requested by the user. The live reference remains the user's selected route.
Report meaningful gains, practical ties, harmful switches, missed opportunities,
coverage, and results by period/day type/incident. No overall accuracy claim
may conceal abstentions or correlated snapshots. Measure incremental value
over MTA, not simply the number of Switch outputs. Unknown outcomes are not
ties. Include candidate families beyond F/G with explicit unavailable reasons.

Deliver reproducible commands, small evidence reports, source manifests,
algorithm outputs, and integration instructions. Clearly distinguish implemented
capability, completed real-data runs, and remaining data-dependent validation.
For teammate integration, version a small sealed aggregate training-profile
bundle when practical. Raw archives, row-level observations and full replay
records remain local; compact reports reference their paths and hashes.

## Ownership, sequence, and replacement

Data acquisition, incident extraction, profile construction, data tests, and
manifests belong under `data/`. Prediction/comparison, evaluation, algorithm
tests, and interface materials belong under `algo/`. All repository content is
English. Credentials remain in ignored local configuration.

After saving this plan, remove old November raw/processed artifacts, old model
binaries, old historical/model/replay source and tests, configurations, and
results. Do not rewrite Git history or remove unrelated course/UI materials.
Retain the shared live integration and contract foundation. Update repository
memory and entry-point documentation to this plan.

Execution: freeze this protocol; replace the old workspace; develop acquisition,
incident/profile processing, and multi-route evaluation in parallel using an
explicit shared schema; run representative checks; process the full month;
freeze development profiles; evaluate; audit and publish truthful results.
