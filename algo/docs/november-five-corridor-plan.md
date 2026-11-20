# Full-October model and November five-corridor analysis

Authorized November 20, 2026. This is a new version and analysis; all previous
October model artifacts, input freezes, evaluations, and examples remain intact.

## Model and dates

- Fit the existing historical endpoint-error model on October 1–31, 2026, in
  America/New_York. Keep the original component scope, hierarchy, support gates,
  and recommendation thresholds. Document unsupported exact components rather
  than claiming that all candidate segments have direct training support.
- Build a separate sealed predictive artifact. Recompute training eligibility
  and aggregation; do not relabel the monthly descriptive artifact as trained.
- Require training endpoint confirmation before November 1, 00:00 local time.
  Purge physical trains and unplanned incident families crossing the training
  boundary, using all November 1–18 input-only inventories to detect overlap.
  This preserves independent-family separation for the analysis and is an
  evaluation-informed input-only purge, not a claim that future inventories
  would be available during prospective deployment. November outcome labels
  never contribute to fitting.
- Analyze November 1–18, following the user's revised end date. Preparation may
  retain November 19; it is outcome boundary evidence only for November 18
  journeys, never an evaluated departure date or a daily-mean contribution.
  Preserve missing dates and boundary censoring. Do not substitute outcomes.
- November 2–15 was examined during the superseded earlier project. Report
  November 16–18 separately and disclose the prior exposure of November data;
  do not describe the complete period as an untouched test set.
- Use timezone-aware instants throughout, including the November 1 clock
  change. Preserve UTC capture times and local date/time labels.

## Fixed five corridors

Reuse the route identities, Google-selected Stay paths, candidate lines,
station mappings, and walking assumptions from
`data/config/google-corridors.json` and
`data/config/incremental-extra-corridors.json`:

| Corridor | Fixed Stay service |
|---|---|
| Hayden LIC Apartments to NYU Tandon | F |
| Grand Central area to Brooklyn Borough Hall | 5 |
| Court Square Park to Times Square | 7 |
| Times Square to Brooklyn Borough Hall | 2 |
| Port Authority area to NYU Tandon | A |

The 29 supplied candidate paths are not an exhaustive historical route search.
The November 20 Google captures define path choices, not historical fastest
routes or historical journey durations. No new Google query is needed.
Same-platform 5-to-4 substitution remains valid. Port Authority A/C retains
the shared 120-second platform-access assumption, with coupled 0/240-second
sensitivity reported separately from the baseline.

## Service-delay Stay/Switch evaluation

1. Identify applicable unplanned disruption and severe-service notice versions
   using only information available at each decision time. Confirm the exact
   line, direction, and segment; mixed notices must not transfer severe wording
   from one service to another. Planned and unresolved exposure stay separate.
   Severe qualification includes explicit severe-delay wording or complete
   unplanned loss of the fixed Stay through-service. Preserve that distinction
   in the review reasons; partial short turns remain ordinary disruption unless
   a severe clause applies. A closure with no feasible Stay forecast remains in
   exposure/exclusion counts rather than disappearing from the coverage report.
2. Select the first applicable checkpoint and five-minute checkpoints through
   two hours while the incident remains applicable. Include carried-in active
   October incidents as an explicitly separate group. Preserve all exclusions.
3. Freeze selected inputs, notice qualification, code, thresholds, predictions,
   model hash, and source hashes before scoring outcome labels. Report one
   earliest input-selected representative per corridor/incident separately
   from all checkpoints. Shared incidents across corridors are not independent.
4. Compare unmodified MTA, time-conditioned profiles, and incident-conditioned
   profiles on identical candidate sets. A predicted saving of at least 300
   seconds triggers Switch. Historical differences within +/-180 seconds are
   practical ties.
5. Compare the actual selected journeys of both policies, including the subset
   where raw MTA says Stay and the new model says Switch. Separately report
   model Switch versus its own Stay, missed opportunities when fully scorable,
   abstentions, missed boardings, unknown outcomes, and severe-stage results.
6. Apply a new, predeclared outcome-quality gate: every required boarding and
   alighting endpoint must have its last-observed time within 180 seconds of
   that endpoint's final prediction proxy, in addition to all existing quality,
   identity, chronology, and actual catchability checks. Require a finite
   archived receipt confirmation and `confirmation_status=CONFIRMED` for each
   endpoint. Failed or missing
   endpoints remain unknown; they are never counted as successful or tied.

Raw-MTA advice means this project's rule applied to unmodified feed estimates;
it is not an official MTA recommendation. Outcomes concern exact selected
trains. Audit large gains for an earlier catchable Stay train and report that
qualification; a fixed-train gain alone is not proof of adaptive Stay-on-line
savings. Do not change frozen counts silently.

## Daily peak-period ETA errors

Use the five fixed Stay paths and a predeclared 15-minute departure grid on
every available date, independent of service problems or outcome availability:

| Period, New York local time | Departure times per date |
|---|---:|
| Morning, 06:00–10:00 | 16 |
| Midday, 11:00–14:00 | 12 |
| Evening, 16:00–20:00 | 16 |

The complete target is 3,960 corridor/checkpoint observations and 270 daily
corridor/period cells. Midday is an analysis window, not a claim of an
empirically established ridership peak.

For the exact raw-MTA-selected Stay journey, calculate:

`signed ETA error = final inferred destination arrival - forecast destination arrival`

Both include the declared access, transfers, and egress. This is a complete
journey residual; do not add unrelated endpoint means or add a second delay
already embedded in the realtime ETA. Positive-only error is `max(error, 0)`
over all comparable observations, not the mean among delayed journeys only.

Report signed mean, positive-only mean, distribution, and usable/unknown
coverage. The primary mean weights the regular departure checkpoints equally,
representing a user leaving during that period. Also report an event-balanced
mean using the earliest input-selected checkpoint per physical train sequence,
corridor, local date, period, and forecast-duration stratum. Deduplicate before
opening outcomes. Retain support counts to expose repeated-train dependence.

Provide daily tables and pooled corridor/period tables, separate weekday,
Saturday, and Sunday summaries, and 0–15/15–30/30–60/60+ minute forecast-duration
strata. A pooled mean reflects the observed mix rather than a standardized
forecast horizon. Apply the same endpoint-quality and catchability rules as
the incident replay; missing or missed journeys are not zero delay.

## Deliverables and verification

- Data acquisition, projection, profile fitting, peak statistics, provenance,
  tests, and data reports remain under `data/`.
- Stay/Switch inference, evaluation, tests, and reports remain under `algo/`.
- Keep large source/normalized artifacts local and ignored; commit reusable
  code, modest model artifacts, manifests, and reviewable reports as appropriate.
- Verify original experiment hashes, exact date coverage, no November fitting
  leakage, input/output separation, same-cutoff route feasibility, denominators,
  and timezone boundaries. Independently review new outputs before delivery.
- All repository content is in English. Final MTA records remain screened
  prediction proxies, not independently measured passenger trips.
