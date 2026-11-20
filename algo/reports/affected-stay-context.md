# Why the affected-route Stay replay is a separate experiment

The original October benchmark asks whether a correction improves the route
that unmodified MTA already considers fastest at the same information cutoff.
It does not necessarily test a commuter whose intended route is disrupted.
None of its selected Stay references had definite applicable severe exposure.
That does not mean October lacked severe disruptions.

The source month is October 1–31. Development statistics use October 1–17;
validation and final test use the following two weeks. Keeping the latter
outcomes out of development prevents testing a profile against its own history.
The supplemental replay reuses the unchanged predictions and exact selected
trains from those held-out weeks. It changes the Stay route, not the predictor,
training data, Switch margin, walking assumptions, or outcome rules.

## Contemporaneous severe exposure

Across the original 385 primary checkpoints, 60 had at least one candidate
classified as definitely severe-affected: 172 route/checkpoint pairs across
seven incident families. These are correlated route observations, not 172
independent disruptions. Sensitivity and alternate-threshold copies are excluded.

The [official-text review](october-affected-stay-text-review.json) checks the
actual route and direction against each contemporaneous notice version before
the new evaluation is scored. It excludes 22 false severe assignments:

- On October 22, a later notice describes uptown R as severe, but downtown R
  and N in both directions as ordinary delays. Sixteen southbound reference
  observations therefore do not qualify at those later checkpoints.
- On October 30, a notice describes N/W as severe and R as ordinary delays.
  Six R-only reference observations do not qualify; affected N/W legs remain.

The confirmed cohort contains 150 route/checkpoint pairs at 54 distinct
checkpoints across seven incident families: 71 validation pairs and 79 test
pairs. Of these, 118 have fresh comparison evidence before changing the
reference. The other 32 retain their last-observed evidence state; text review
does not make an old alert fresh.

This review is limited to the observed notice versions. It is not an automatic
replacement severity classifier. The frozen classifier's mixed-route and
directional wording limitation remains documented. An official severe notice
establishes a service condition, not a measured delay for every selected train.

## Why the original ten conditional Switch outcomes were unknown

The original test's incident-profile mode produced 14 timing-only Switch
diagnostics, of which four had comparable endpoints and ten did not. Audit of
the exact selected-train evidence found:

| Reason among those ten cases | Cases | Detail |
|---|---:|---|
| Selected train cannot be caught under the final endpoint proxy | 7 | Four missed transfers; three missed initial boardings. Six on the Switch route, one on Stay. |
| Endpoint record excluded by the frozen quality rules | 5 | Four with schedule changes, three also rewrites; one with arrival forecast after stop-disappearance confirmation. One changed-schedule case also lacks endpoint/confirmation evidence. |
| Both categories occur in the same case | 2 | The categories overlap, so the total is ten, not twelve. |

Three cases fail on Stay only, five on Switch only, and two on both. These
counts are from primary test records in
`algo/local/october/october-test-cases.jsonl.gz`.

A missed train is a known catchability problem, not merely a missing archive.
The evaluator does not use hindsight to substitute the next train, so the
complete journey's arrival time remains unknown. Likewise, a quality-rule
exclusion is not proof that every underlying timestamp is wrong. Neither kind
of unknown is a success or practical tie. Alert freshness is a separate issue
from endpoint outcome coverage.

## How to interpret the supplement

Read the [validation supplement](affected-stay-validation.md) and
[test supplement](affected-stay-test.md). They retain every qualified case,
including abstentions and unknown outcomes. Examples are chosen by input-only
chronological rules, not by whether switching wins. This is a post-hoc response
to a new product question, not a replacement for the original frozen benchmark.

The separate [observable illustrations](affected-stay-illustrations.md) show
the earliest scorable strict Switch per test incident, and retain an unknown
example for the incident with none. These additional examples are explicitly
outcome-selected for readability; they do not define the evaluation population.
The full test has 56 strict incident-profile Switches, 13 with comparable
outcomes from three incidents and 43 unknown, plus 23 abstentions. The 13
comparable pairs all show gains beyond three minutes; this is not a general
100% success rate.

Compare unmodified MTA and the historical-correction modes separately. Finding
a faster alternative to a severe-affected Stay route does not by itself show
that historical corrections improve on MTA. Report the number of comparable
outcomes and independent incident families alongside any observed gains.
All scored arrivals remain screened final MTA prediction proxies with authored
walking times, not independently observed passenger journeys.
