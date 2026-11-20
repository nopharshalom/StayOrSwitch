# Originally fastest route: delay and Switch outcomes

Two fully comparable same-run samples show that the originally fastest route
can remain preferable after its train's ETA slips: switching would have been
6 minutes 45 seconds and 14 minutes 45 seconds slower. The current algorithm
correctly kept STAY for both comparisons.

The broader route-level search also found a missed opportunity: on
October 26, switching from the originally fastest 4/5 route to F would have saved
7 minutes 13 seconds in the screened final MTA replay. The current algorithm
recommended STAY. This establishes one missed opportunity, not a successful
algorithm recommendation or a general Switch success rate.

All dates below are in America/New_York. Journey durations include authored
access/egress walking and start from the same street origin at the reassessment
time. The user is not boarded. Final MTA predictions are screened outcome
proxies, not independent measurements of a passenger's actual journey.

## Comparable route-level example

Origin: Grand Central at East 42nd Street / Lexington Avenue.
Destination: Borough Hall at Court Street / Joralemon Street.
The supplied candidates are direct 4/5; 7 then 2/3; walking to Times Square then
2/3; and walking to Bryant Park, taking F to Jay Street, then walking to Borough
Hall. Compatible 4/5 trains are one route, rather than artificial Switch choices.

At **03:14:59 on October 26**, before the recorded official problem boundary,
the default route was clearly fastest among these candidates:

| Candidate | Original MTA journey forecast |
|---|---:|
| Direct 4/5 | **29.77 min** |
| Walk to Times Square, then 2/3 | 45.68 min |
| Walk to Bryant Park, then F | 47.28 min |
| 7 then 2/3 | 67.70 min |

At **03:21:00**, the applicable official notice reported 4 delays in both
directions while investigating an activated train brake near Bowling Green.
The fixed Stay route remained 4/5. Its best catchable train was now a later
4 service run. Raw MTA still ranked this route first at the new departure time.

| Evaluation at reassessment | Stay: direct 4/5 | Alternative: F |
|---|---:|---:|
| Raw MTA forecast | **41.61 min** | 42.46 min |
| Current incident-profile forecast | 45.69 min | **45.40 min** |
| Screened final MTA replay | 46.96 min | **39.74 min** |
| Arrival at the common street destination in the replay | 04:07:58 | **04:00:45** |

The algorithm forecasts only **17 seconds** of F advantage, below the unchanged
five-minute Switch threshold, and therefore recommends **STAY**. The observed
proxy difference is **433 seconds in favor of F**, a meaningful missed
opportunity under the predeclared three-minute outcome-tie boundary.

This comparison preserves the exact forecast-selected trains. The selected
4 run's Borough Hall arrival was forecast at 04:00:37 and its usable final proxy
was 04:05:58: **321 seconds later**. F's full-journey proxy was 163 seconds earlier
than its own contemporaneous raw forecast. Together these reverse the raw MTA
ranking by 484 seconds. Historical correction did not identify the full gap.

### What this example does and does not show

It meets the route-level question: the previously fastest route was affected
by an official delay and remained the current raw-MTA default. Its selected
train's final arrival proxy was later than its current forecast, while the
alternative had a faster usable proxy outcome.
It does **not** show that the original train selected at 03:14:59 became delayed
by the entire increase in remaining journey time.

The earlier 4 train became uncatchable as the query time advanced. The later
train was already visible in the earlier feed, and its ETA actually improved
by 53 seconds between queries. The apparent 11.84-minute T0-to-T1 increase is
a changed-train/headway effect, not measured incident delay. Keep that separate
from the selected later train's 5.35-minute forecast error after T1. See the
[raw chronology audit](preincident-brooklyn-headway-audit.json).

Direct 4/5 assumes three minutes of access and two minutes of egress. F assumes
ten minutes of access and eight minutes of egress. The original winner stays
fastest in 17 of 18 single-component walking perturbations of plus/minus two
minutes. These assumptions limit precision and are not measured walking times.

## Negative comparisons and denominators

The [complete route-level study](preincident-brooklyn-test.md) keeps all 31
input-selected checkpoints across 11 official incident families. The
[predeclared clear-default subset](preincident-brooklyn-clear-default.md) has
24 checkpoints across 10 families; the other seven checkpoints had only a
17-second original lead and are reported separately.

For the clear-default subset, the current incident-profile algorithm produced
19 STAY decisions, five UNDETERMINED decisions and **no Switch recommendation**.
Its forecast-best alternative had comparable outcomes at ten checkpoints:
two gains and eight losses exceeding the three-minute practical-tie boundary;
14 other comparisons were unknown. The two gains repeat the same October 26
4/F train pair, so they represent **one opportunity**, not two independent wins.

A negative illustration is October 25 at 02:32:32. The originally fastest 4/5
route had an applicable downtown delay notice. The current model predicted
46.67 minutes for Stay versus 43.02 for F and kept STAY. The usable proxies were
44.40 versus 47.95 minutes: switching to F would have been **3.55 minutes slower**.
The time-profile-only mode did recommend Switch and lost that amount. A delay
therefore does not by itself imply that changing routes improves the trip.

Examples with usable outcomes are illustrations, not an outcome-filtered cohort.
The full frozen reports retain every selected case, exact chosen trains, modes,
negative results, and unknown outcomes. Raw MTA, time-profile and incident-profile
predictions are evaluated without retraining or changing recommendation margins.

## Stronger same-run check

The separate fixed-grid searches require the original fastest route to retain
the same encoded service run as
its best catchable train, with its absolute destination forecast moving later
by at least five minutes. This prevents the headway effect described above.

The initial [Court Square to Times Square search](feed-revision-test.md)
produced two qualifying 7 runs: October 28 with an ETA
revision of +7 minutes 27 seconds, and October 29 with +5 minutes 24 seconds.
All three algorithm modes recommended STAY. Both runs' final boarding-time
records failed the frozen reliability screen; one arrival record also failed.
Their alternative outcomes exist, but neither full Stay/alternative comparison
can be scored. They remain **unknown**, not wins, losses or evidence that no
delay occurred. These cases had no applicable official 7 disruption notice and
do not validate severe-service advice.

The source records exist: the rejected final departure predictions were 50 and
64 seconds after the respective stop had already been marked past. The issue
is internally inconsistent outcome evidence, not missing archive files. See
the [outcome audit](feed-revision-outcome-audit.json); the separate
[source audit](feed-revision-source-audit.json) verifies the as-of ETA revisions.

### Comparable same-run cases: Grand Central to Borough Hall

After the two unusable Court Square outcomes, a separate coverage-driven
[Brooklyn extension](feed-revision-brooklyn-test.md) reused the four already
declared paths and identical fixed grid, lags, thresholds and selection rules.
It retained all five qualifying pairs, deduplicated to three service runs using
the earliest reassessment and then earliest anchor, before reading their labels.
No outcome or gain filter selected the runs. This expansion is explicitly
post-hoc, and the original two unknown cases remain in their frozen report.

All three original winners were clearly faster than their alternatives:

| Reassessment | Original cutoff | Original 4/5 forecast | Next-fastest original forecast | Same-run ETA revision at reassessment | Final arrival proxy later than original forecast |
|---|---|---:|---:|---:|---:|
| Oct 25, 01:05 | 01:00 | 37.00 min | 49.28 min | +6 min 41 sec | **8 min 57 sec** |
| Oct 29, 10:00 | 09:50 | 29.00 min | 38.57 min | +9 min 05 sec | **6 min 38 sec** |
| Oct 29, 15:20 | 15:10 | 27.30 min | 41.57 min | +8 min 25 sec | **7 min 02 sec** |

The current incident-profile algorithm produced these results. The alternative
is its forecast-best non-Stay route, not the hindsight winner.

| Reassessment | Forecast Stay / alternative | Model advice | Final-proxy Stay / alternative | Effect of switching |
|---|---|---|---|---|
| Oct 25, 01:05 | 41.86 / 46.91 min, F | STAY | 40.95 / 47.70 min | **6 min 45 sec slower** |
| Oct 29, 10:00 | 29.63 / 39.31 min, 7 then 2/3 | STAY | 25.63 / unknown | **Unknown** |
| Oct 29, 15:20 | 24.97 / 36.70 min, F | STAY | 24.33 / 39.08 min | **14 min 45 sec slower** |

All three prediction modes retain the same delayed Stay train and recommend
STAY for all three runs. Only the 10:00 case has an applicable official delay
notice, concerning police activity; none is classified as severe. The other
cases are direct feed-forecast revisions without an applicable official notice.
The [source audit](feed-revision-brooklyn-source-audit.json) verifies the exact
same-run forecasts and catchability at both cutoffs.

Across the two same-run ODs, there are five distinct runs: two complete
Stay/forecast-best-alternative comparisons and three unknowns. Both complete
comparisons favor Stay. There are no Switch recommendations in this cohort,
so it cannot supply a Switch-success percentage.

## Interpretation

The comparable example demonstrates that meaningful route-level opportunities
exist and that the current model can miss them. It does not establish superiority
over raw MTA or a reliable success rate. The stricter same-run study is an
additional diagnostic, not a reason to erase the valid route-level comparison.
All searches are post-hoc exploratory analyses of a previously examined test
week, with inputs frozen before each new cohort's outcome scoring.
