# Does the model find useful Switch advice when raw MTA says Stay?

The denser three-corridor replay finds **two ordinary-service-problem examples
with a meaningful, near-event-supported Grand Central 5-to-4 saving**, plus
the previously qualified Court Square fixed-train example. It does not supply
five to ten independent, well-supported route-level examples of this narrower
model advantage.

Here, raw MTA “Stay” means the project's unchanged five-minute Switch rule
applied to unmodified MTA predictions. It is not an official MTA routing
recommendation. A 5-to-4 change at the same boarding/alighting stations is
counted as a valid Switch without an invented transfer penalty.

## Scope and overall results

The [protocol](../docs/incremental-switch-experiment.md) adds a fixed five-minute
grid through two hours after the same 49 previously confirmed corridor–incident pairs,
retaining all original notice-receipt checkpoints. Of 1,335 planned checkpoints,
614 have exactly a previously reviewed contemporaneous notice/route scope;
663 have no applicable as-of problem and 58 have an unreviewed exact scope.
All 322 earlier confirmed checkpoints retain identical predictions. Inputs were
frozen and independently audited before new outcome scoring.

| Comparison | Advice/action pairs | Comparable outcomes | Meaningful gains | Practical ties | Meaningful losses | Unknown complete gains |
|---|---:|---:|---:|---:|---:|---:|
| Model Switch versus its own Stay prediction/selected journey | 76 | 33 | 25 | 8 | 0 | 43 |
| Raw MTA Stay versus model Switch, exact policy-selected journeys | 13 | 5 | 3 | 2 | 0 | 8 |
| All concrete raw-MTA/model action pairs, including Stay and Switch | 189 | 116 | 12 | 102 | 2 | 73 |

Outcome differences within ±3 minutes are practical ties. The 13 disagreement
checkpoints span nine corridor–incident families and include repeated near-
identical train pairs. The three meaningful incremental gains come from three
families, but the Court Square result is only a fixed-train comparison.
None of the 49 primary event representatives has raw-MTA Stay/model Switch.
Across those primary representatives, the model makes four Switch suggestions:
one comparable saving and three unknowns; 14 comparable policy pairs all tie.
Within the 13 raw-Stay/model-Switch disagreements, four unknown cases have
unusable Stay endpoints and four have unusable Switch endpoints. None of these
eight unknown disagreement cases is a known missed selected train.

The 25/33 observed own-Stay gains are **not a general success rate**. Forty-three
of 76 Switch recommendations have unknown complete gains, including eight
recommended journeys that miss a selected boarding/transfer. Missing/unreliable
Stay endpoints occur in 31 and Switch endpoints in 14 of those unknown cases;
these counts overlap. Repeated checkpoints are not independent trips or trials.
The 12 gains and two losses in the matched-policy comparison likewise describe
this observed subset, not citywide model performance.
One of those 12 recorded gains has a material endpoint-quality exception:
`grandcentral_boroughhall--lmm-alert-273712--1793134102725`, October 27 at
16:48:22. Raw MTA recommends switching to 4 while the model stays on 5, with
a recorded 626-second gain, but the selected 5 boarding prediction persists
for **971 seconds** before its last observation. The arrival endpoint is
near-event. The [independent audit](incremental-switch-audit.json) identifies
this stale boarding label; its benefit must be excluded from any conservative
supported-gain count. The frozen total remains 12, and this exception does not
affect the narrower raw-Stay/model-Switch examples. All 33 comparable model
Switch pairs have endpoint ages at most 133 seconds; all five comparable
raw-Stay/model-Switch pairs are within 92 seconds. These age checks qualify
the recorded results without changing the cohort or labels.

The two matched-policy losses occur on October 26 at 10:01 and 10:44 on Grand
Central → Borough Hall: raw MTA recommends Switch while the model says Stay,
losing 7m19s and 5m18s respectively under the recorded proxies. They remain in
the denominator. The model can miss useful switching opportunities as well as
find them.

## Positive disagreement examples

All times are New York local time in 2026. Predictions and replay durations
include declared access/egress walks. Raw and model predictions can select
different trains on the same path; each outcome uses its own forecast-selected
train, without hindsight replacement.

| Historical cutoff | Corridor | Stay → Switch | Contemporaneous service problem | Raw predicted Stay / Switch | Model predicted Stay / Switch | Policy-selected outcome Stay / Switch | Proxy saving |
|---|---|---|---|---:|---:|---:|---:|
| Oct 29, 15:49:57 | Grand Central → Borough Hall | 5 → 4; both Grand Central–Borough Hall | Downtown 2/5 delays after a signal problem at Freeman St | 29.89 / 27.20 min | 29.71 / 23.99 min | 29.72 / 24.20 min | **5m31s** |
| Oct 29, 16:10:55 | Grand Central → Borough Hall | 5 → 4; both Grand Central–Borough Hall | Both-direction 2/5 delays after EMS assistance at Jackson Av | 31.12 / 26.17 min | 30.94 / 25.75 min | 27.74 / 23.64 min | **4m06s** |
| Oct 30, 05:51:23 | Court Square Park → Times Square | 7: Court Sq–Times Sq → F: Court Sq-23 St–42 St-Bryant Pk, then walk | Hudson Yards-bound 7 delays during an unauthorized-person-on-tracks investigation at 46 St-Bliss St | 22.27 / 28.47 min | 23.38 / 15.22 min | 106.52 / 23.69 min | **82m50s, fixed-train only** |

For Freeman St, raw MTA's best alternative advantage is 2m41s; the model's is
5m43s. The model selects an earlier 4 train than the unmodified feed's forecast
selection. The replayed 4 boarding slack is 37.20 seconds after the configured
walk. This is not an added same-platform transfer penalty; it is the remaining
time to catch the selected train from the street origin.

For Jackson Av, raw MTA already predicts a 4m57s advantage, only three seconds
below the five-minute Switch threshold. The model predicts 5m11s and crosses
that boundary; both modes identify the same 4 train. The actual-proxy saving
is 4m06s and boarding slack is 42.35 seconds. This is a valid but borderline
decision-rule difference, not evidence of a large raw-MTA ETA error.

Court Square's 82m50s difference includes 92.54 minutes waiting for one
originally selected 7 train. Other 7 trains have earlier endpoint evidence, so
this number does not establish savings against a passenger who stays on the 7
and takes an earlier available train. Its notice is ordinary-delay wording at
05:51; severe wording arrives later. See the
[original large-delay audit](google-corridors-large-delay-audit.json).

## Other raw-Stay/model-Switch checkpoints

The complete [13-case record](incremental-switch-cases.json) retains every
disagreement, not just positive illustrations.

| Cutoff | Stay → model Switch | Service problem | Complete policy gain |
|---|---|---|---|
| Oct 26, 16:52:20 | Grand Central 5 → 7 then 3 via Times Sq | Downtown 4/5 delays after NYPD assistance for a disruptive person at 59 St | Unknown: selected Switch 7 endpoint unusable |
| Oct 27, 08:14:02 and 08:14:03 | Grand Central 5 → 6 then R via Union Sq | Downtown 4/5 delays after a train's brakes activated at 138 St-Grand Concourse | Unknown: selected R endpoints have schedule changes; near-identical repeated checkpoints |
| Oct 28, 10:36:58 | Grand Central 5 → 4 | 23 St brake incident; 6 express reroute and downtown 4/5 delays | Unknown: Stay endpoints unusable |
| Oct 28, 17:29:55 | Grand Central 5 → 4 | Urgent track maintenance near 3 Av/149 St; both-direction 2/5 delays | +2m20s, practical tie |
| Oct 28, 17:49:55 | Grand Central 5 → 7 then 3 via Times Sq | Same urgent track-maintenance incident | Unknown: selected Switch 7 endpoint unusable |
| Oct 29, 08:32:45 and 08:34:45 | Grand Central 5 → 4 | Both-direction 2/5 delays after a brake incident near Nereid Av | Unknown: missing Stay endpoints; repeated selected train pair |
| Oct 29, 18:03:32 | Grand Central 5 → 4 | Both-direction 2/3/4/5 delays after an unauthorized person on tracks at Franklin Av | +2m35s, practical tie |
| Oct 30, 05:41:23 | Court Square 7 → F via Bryant Pk | Unauthorized person on tracks at 46 St-Bliss St | Unknown: Stay boarding endpoint unusable |

The Grand Central alternatives all finish at the same Borough Hall destination;
the 6-to-R path alights at Court St and includes its recorded egress walk.
These unknown and tie cases must not be presented as five to ten successes.

## Interpretation and reproducibility

The model has limited incremental evidence over the raw-MTA decision rule in
these corridors. It provides some useful extra Switch advice, but often makes
the same practical decision, sometimes misses a better Switch, and leaves many
outcomes unverifiable. The nine severe/closure checkpoints in the denser cohort
still do not supply a quantified successful severe Switch.

Historical outcomes remain screened final MTA predictions plus fixed walking
assumptions, not independently observed passenger arrivals. Supplemental endpoint
age, boarding and adaptive-Stay audits qualify positive results without changing
the frozen cohort. No new walking-sensitivity replay was run for this grid.

- [Full results and denominators](incremental-switch-test.json).
- [Selection freeze](incremental-switch-selection-frozen.json).
- [Input and outcome audit](incremental-switch-audit.json).
- [Positive-case endpoint audit](incremental-switch-endpoint-audit.json).
- [All raw-Stay/model-Switch case details](incremental-switch-cases.json).

Eight new safeguard tests cover exact scope reuse, fixed grid membership,
correct policy baseline, unknowns and outcome-tie boundaries. Original
Google-corridor producers and results remain unchanged.
The independent input/outcome audit passes 360,233 checks. A further 530-check
endpoint audit covers all five comparable disagreement cases: all 20 distinct
used endpoints match raw CSV values, lie 22–92 seconds from their last
observation, and disappear within 16 seconds of that final observation. It
finds no known earlier usable exact-line 5 arrival for the Grand Central
illustrations, without claiming complete archive coverage. Court Square's
earlier 7 alternatives remain the explicit adaptive-Stay limitation above.
