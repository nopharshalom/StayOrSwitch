# Interpretation of the visible-feed passenger replay

Read this note with the [complete results](november-feed-replay-test.md),
[execution protocol](../docs/november-feed-replay-plan.md) and
[outcome-quality addendum](../docs/november-feed-outcome-quality-addendum.md).
This version implements the user's instruction to choose A from the current
feed and revise that choice when subsequent information changes the situation.
It does not require proving the actual order of every unselected train.

## What changed and what stayed fixed

At each platform, the executor reads the latest fresh capture and chooses the
compatible service with the earliest raw departure forecast. An advertised
expired forecast is due now. Later feed updates may change the intended train;
once a usable departure supports boarding, the executor follows that train.
Missing final records for unselected trains do not block comparison. A selected
train's missing departure, disappearance without resolved movement, invalid
arrival or a feed gap still leaves its outcome unknown. The executor never
chooses a replacement merely because its final record is more convenient.

The full October 1–31 model, 120-second planning margin, five corridors and
exact prior predictions remain unchanged. The cohort contains 2,306 departure
checkpoints on November 2–6, 9–13 and 16–18, with 197 earliest corridor/notice-
family representatives. Model advice still contains 743 Stay, 339 Switch and
1,224 undetermined decisions. The undetermined decisions are distinct from
unknown historical outcomes for a concrete Switch recommendation. No model
was refitted and no recommendations were generated during this change.

The five-minute predicted saving threshold and the plus/minus three-minute
outcome tie band are unchanged. A practical tie is an immaterial difference,
not a meaningful loss. Multiple checkpoints may share trains or incidents;
neither all checkpoints nor publisher notice IDs represent independent faults.
All dates have now been examined, so this is a post-hoc replay comparison.

## Results and comparison with the previous evaluator

| Scope | Model Switch | Gain >3 min | Practical tie | Loss >3 min | Unknown |
|---|---:|---:|---:|---:|---:|
| All weekday checkpoints | 339 | 78 | 70 | 25 | 166 |
| Earliest representatives | 34 | 10 | 8 | 3 | 13 |
| Qualified severe | 51 | 5 | 8 | 2 | 36 |
| November 16–18 | 49 | 5 | 12 | 1 | 31 |

The same 339 Switch recommendations previously had 40 comparable outcomes
and 299 unknowns. They now have 173 comparable outcomes and 166 unknowns:
coverage rises from 11.8% to 51.0%. All 40 previous comparable classifications
are retained. The 133 newly comparable records contain 55 gains, 57 ties and
21 losses. The change recovers usable comparisons without treating unknowns
as successes or removing negative results.

Among the 173 comparable records, 78 (45.1%) gain more than three minutes and
148 (85.5%) either gain or tie. The remaining 25 (14.5%) lose more than three
minutes. Three of the 78 gains depend on the declared unverified-waiting
assumption; the other 170 comparable records contain 75 gains, 70 ties and
25 losses. The primary and severe comparable groups have no such conditional
waits. These proportions describe available repeated-checkpoint evidence,
not an overall real-world success probability.

The 166 unknown Switch comparisons comprise 93 incomplete selected routes
and 73 complete selected routes whose Stay outcome remains incomplete. Their
exclusive reasons are 84 missing/unusable selected departures, 67 unresolved
selected disappearances, nine missing/unusable selected arrivals, two
implausible selected ride times and four unusable feed captures. Unselected
trains' missing records are no longer the reason for withholding a comparison.

## Incremental model value and severe service problems

For the narrower raw-MTA Stay / model Switch question, 61 cases contain
13 gains, 14 ties, four losses and 30 unknowns. The two earliest representatives
contain one tie and one unknown. In the broader paired comparison with raw
MTA decisions, 727 comparable records contain 18 model gains, 694 ties and
15 losses, with another 292 concrete-action pairs unknown. At the earliest
representatives, 79 comparable records contain zero gains, 78 ties and one
loss, with 37 additional unknown pairs. These results do not establish a
consistent model advantage over the raw-MTA policy.

All five severe own-Stay gains occur at different checkpoints of the same
November 12 F-line water-removal incident at Jamaica–179 St. They switch from
F via Court Sq–23 St/Jay St–MetroTech to G via Court Sq/Hoyt–Schermerhorn, then
walk to Tandon. The inferred savings are 6m10s, 6m10s, 5m00s, 19m15s and
11m30s. For example, at 16:43:33 New York time, the complete F route takes
56m27s and G takes 37m12s under the replay assumptions. These are five
checkpoints of one incident, not five independent severe disruptions.

Raw MTA also recommends Switch in those five severe gains. Across all 43
comparable severe model-versus-MTA policy pairs, outcomes tie. The narrow
severe raw-MTA Stay / model Switch subset contains nine cases: two ties and
seven unknowns, with no supported gain after the malformed C sequence is
excluded. The study supports some beneficial severe route changes while
leaving incremental severe benefit from historical correction unestablished.

## Illustrative raw-MTA Stay / model Switch cases

These examples come from the fixed cohort and do not create a new selected
test set. Times are New York local time. Route totals include the fixed access,
transfer and egress walking assumptions. All listed outcomes have no unverified
selected-waiting interval. Same-platform 5-to-4 changes remain normal valid
Switch choices. A service notice can also affect both alternatives.

| Departure | Corridor | Stay → Switch | Inferred result | Contemporaneous problem |
|---|---|---|---|---|
| Nov 4, 09:40:38 | Times Square → Borough Hall | 2 → 3 | Saves 3m29s | Downtown 2 delays after removal of a mechanically faulty train at Wakefield–241 St. |
| Nov 5, 06:42:17 | Times Square → Borough Hall | 2 → walk to Port Authority, A to Jay St, walk to Borough Hall | Saves 6m12s | Brooklyn-bound 2/5 delays after a signal malfunction near Newkirk Av–Little Haiti. |
| Nov 6, 15:13:03 | Times Square → Borough Hall | 2 → 3 | Saves 3m57s | 2/3 delays after urgent track maintenance near 135 St. |
| Nov 9, 09:24:10 | Grand Central → Borough Hall | 5 → 4 | Saves 10m05s | 4/5/6 delays after a train with activated brakes was moved near Bleecker St. |
| Nov 12, 08:16:38 | Grand Central → Borough Hall | 5 → 4 | Saves 4m24s | Brooklyn-bound 2/5 delays while investigating activated brakes at Newkirk Av–Little Haiti. |
| Nov 10, 11:45:00 | Grand Central → Borough Hall | 5 → 4 | Loses 11m33s | 2/5 delays during a signal problem at 149 St–Hostos, with uptown 4 delays also reported. |

## Evidence quality and remaining uncertainty

The initial internal run exposed a malformed November 18 C-train sequence:
42 St-Port Authority to Jay St-MetroTech took only ten seconds according to
the final predictions. The [original-source audit](november-feed-replay-source-anomaly-audit.json)
found repeated one-second intervals across consecutive downstream stops.
Joint disappearance made individual endpoint freshness checks pass. The
apparent A-to-C saving of 18m47s is not usable evidence of real travel savings.

The corrected replay applies the same geographic screen to every selected
Stay and Switch leg, including old/new advice and margin sensitivities. A
300 km/h straight-line average ceiling rejects collapsed timelines after the
train has been selected. This deliberately generous ceiling is a data-quality
parameter, not a claim about subway speed. No replacement duration or better-
recorded train is substituted. The original prediction views and source
timestamps remain unchanged. The first internal run and its exact producers
are preserved and bound to the corrected freeze; this correction was made
after inspecting its results and is disclosed as such.
Across all supplied paths, the screen rejects 11 route queries involving five
unique train/segment pairs. Ten were previously complete and one was already
unknown; it now stops earlier. In the model Switch comparison specifically,
two apparent gains become unknown. The final count is 78 gains, not the
superseded internal count of 80.

Some successful reconstructions include a period when an intended train's
departure cannot be verified. The executor assumes continued waiting strictly
before that train's currently forecast departure boundary and may update its
choice from a newer feed. These cases are separately marked conditional on
the waiting assumption. Reaching the boundary without selected departure
evidence remains unknown; an unknown due-now departure is unknown immediately.

All remaining durations are screened final MTA prediction proxies plus
authored walking times. They are not independently observed passenger trips.
Unknown outcomes are neither wins nor ties, and observed-case percentages do
not establish a success rate for every recommendation.

## Planning catchability and execution attempts are different

The preserved boarding diagnostic evaluates the trains originally selected
by the prediction process. Its zero missed Switch sequences among 288 usable
checks, with 51 unknown, must not be relabeled as zero misses during the new
execution. At a platform the feed-following passenger may choose a different,
earlier advertised service. If screened evidence later shows that this train
had already departed, the replay records a missed attempt and waits for the
next feed update. Later completion does not erase the missed attempt. The
complete report gives both diagnostics with their respective denominators.
The 339 model Switch route queries contain 30 missed-service attempts and
43 reselection events. These are execution events, not distinct incidents.

The original [daily peak-delay study](../../data/reports/november-weekday-peak-delays.md)
was not recomputed. It retains its original fixed-train interpretation and
must not be presented as a result of this route-execution correction.

## Verification

The full local suites pass: 581 algorithm tests and 305 data tests, run with
`PYTHONPATH=algo:.` using the project Python environment. Focused cases cover
feed-only selection, updates before boarding, due-now behavior, unknown
selected records, conditional waiting, collapsed endpoint timelines and the
absence of outcome-based fallback. Old frozen producers and results are
protected by the [preservation manifest](../../data/manifests/november-feed-replay-preservation.json).

The [aggregate audit](november-feed-replay-independent-audit.json),
[bounded source-case audit](november-feed-replay-case-audit.json) and
[selected-outcome quality audit](november-feed-replay-quality-audit.json)
independently check the reported arithmetic and evidence.
The aggregate audit passes 6,442,928 checks covering counts, arithmetic,
cohort/advice identity, quality transitions and prior-file preservation.
The latter verifies 149,096 assertions across all 15,203 route queries,
including unchanged advice and selection traces through the rejected boarding.
All 12,627 final completed legs pass the bound. The source-case audit checks
361 assertions on six routes spanning gains, losses, recovered and unknown
cases. The preservation manifest retains 381 previously tracked files.
These checks validate consistency with the declared reconstruction policy;
they do not replace independent passenger arrival observations.
