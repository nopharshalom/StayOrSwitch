# Boarding repair: interpretation of the November replay

Read this note with the [complete repaired results](november-repair-test.md)
and [implementation handoff](../docs/boarding-safe-handoff.md). The study keeps
the same October-trained profile, five corridors, 2,306 November weekday
checkpoints and 197 earliest corridor/notice-family representatives. It is a
post-hoc regression on already examined data, including November 16–18.

## Boarding feasibility improved

The new predictor uses a separate boarding gate with a 120-second margin.
Positive historical departure delay cannot make an otherwise uncatchable train
eligible. Transfer feasibility uses conservative arrival readiness. This buffer
does not inflate actual travel duration, and all three prediction policies use
the same rule.

Under the preserved exact-train diagnostic, model-selected missed journeys fall
from 137 to one; missed Switch journeys fall from 51 to zero. The additional
departure-first diagnostic does not require a usable final destination arrival
to identify a missed boarding. It finds 150 failed boarding sequences among
893 evaluable old-model choices, versus one among 936 evaluable repaired choices.
There remain 143 and 146 unevaluable sequences respectively. Among repaired
Switch choices, all 288 evaluable boarding sequences are catchable under the
declared walking and screened-proxy assumptions; 51 remain unevaluable. This is
not a claim that all 339 recommendations are guaranteed catchable in practice.

## Route benefit has much less supporting evidence

The new executor follows a fixed route and can board an earlier or later
compatible service instead of remaining locked to the initially forecast train.
It selects by evidenced departure order, never by eventual fastest destination
arrival. Unknown potentially earlier trains block exact first-service ordering.
Both old and repaired recommendations use this same execution policy.

| Model and evaluator | Switch | Gain >3 min | Tie | Loss >3 min | Unknown |
|---|---:|---:|---:|---:|---:|
| Old model, original exact-train evaluator | 287 | 99 | 16 | 2 | 170 |
| Old model, new route executor | 287 | 15 | 7 | 3 | 262 |
| Repaired model, new route executor | 339 | 23 | 13 | 4 | 299 |

Thus the change from 99 to 23 gains is not a direct before/after accuracy
comparison: both the boarding policy and the meaning of a route outcome changed.
Holding the executor fixed, there are 329 comparable old/new chosen-route
outcomes: five improved, 316 tied and eight worsened. Another 676 concrete-action
pairs remain unknown. Better boarding feasibility does not establish better
arrival time on every route.

At the 197 representative checkpoints, 34 repaired Switch recommendations
produce three gains, two ties, one loss and 28 unknowns. The severe subset has
51 Switch recommendations with no complete route-level comparison. This does
not establish either severe-Switch success or failure.

The raw-MTA baseline also uses the two-minute boarding gate. Among 374 comparable
model-versus-raw-MTA route choices, there are two gains, 366 ties and six losses;
645 further concrete-action pairs remain unknown. Incident profiles have not
shown a reliable advantage over that baseline or over time-only history.

## Unknown ordering is not the same as an absent feed

Of the repaired model's 299 unknown Switch comparisons, 190 have an incomplete
chosen route and 109 have a completed chosen route but incomplete Stay. In 290
of those comparisons the exclusive failure reason is unresolved earlier
boarding; eight involve feed continuity and one lacks the first boardable
train's destination arrival.

The archive may contain an earlier-visible candidate with a departure forecast
far in the future but no usable final departure record. A forecast alone cannot
prove the actual ordering used by this strict evaluator. For example, the
bounded source audit found blockers whose raw departure forecasts were roughly
30 or 128 minutes away, with unusable endpoint evidence. The evaluator does not
claim these trains actually arrived first. It reports that first-service order
cannot be established under the declared evidence rules. Some of the unknown
count therefore reflects conservative identification requirements as well as
incomplete or unusable historical records.

The observation window and sampled-feed continuity assumptions are documented
in the [archive guide](../../data/docs/november-route-archive-v2.md). A disappearance
alone proves neither arrival nor cancellation. An explicit cancellation or
endpoint skip before platform readiness can resolve an old candidate; the
[execution correction record](november-repair-execution-correction.json)
preserves the initial internal run and documents the correction of that
previously unsupported state transition. Predictions, model, cohort, thresholds
and training stayed unchanged during this correction.
The corrected rerun changes no route status, duration or recommendation outcome
in this cohort; its purpose is to fix the evidenced state transition, not to
claim a numerical coverage improvement where none occurred.

## Illustrative incremental decisions

These cases use a raw-MTA Stay decision and a repaired model Switch decision.
They illustrate recorded outcomes rather than forming a new selected test set.

| New York time | Corridor | Stay → Switch | Route outcome | Service problem |
|---|---|---|---|---|
| Nov 4, 09:40:38 | Times Square → Borough Hall | 2 → 3 | Saves 3m29s | Downtown 2 delays after removal of a mechanically faulty train at Wakefield–241 St. |
| Nov 6, 15:13:03 | Times Square → Borough Hall | 2 → 3 | Saves 3m57s | 2/3 delays following urgent track maintenance near 135 St. Both alternatives can share exposure. |
| Nov 10, 11:02:13 | Port Authority → Tandon | A → C | Loses 4m20s | Downtown A/B/C/D signal malfunction near 135 St. |

The original daily peak-delay tables remain unchanged: they describe a separate
fixed-train ETA-residual study. They must not be relabeled as results of this
new route execution. All inferred times remain final MTA prediction proxies
plus authored walking assumptions, not independent passenger measurements.

## Verification

All 165 new focused and independent tests pass. The
[independent aggregate audit](november-repair-independent-audit.json) verifies
1,270,297 assertions covering forecast gates, transfer arithmetic, cohorts,
all result summaries, paired policies and preservation of 351 original files.
The [bounded execution audit](november-repair-execution-example-audit.json)
checks eight gain, loss, recovered and unresolved cases against 17 original
normalized snapshots and 67 endpoint records. It also independently checks
candidate ordering, including unresolved earlier-service blockers. These
checks establish consistency with the declared replay, not independent proof
of passenger travel times.
