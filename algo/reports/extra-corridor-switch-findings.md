# Two additional corridors: incremental Switch findings

These two corridors complete the user's five-corridor limit. They add one
meaningful fixed-journey proxy gain where raw-MTA policy says Stay and the
incident-profile policy says Switch. That gain depends on the declared
origin-to-platform access assumption. The other nine comparable disagreements
are practical ties under the unchanged three-minute outcome boundary.

Google was queried on November 20, 2026 at approximately 11:42:28 New York time.
Its current default selects the Stay path, not the historical outcome duration.
The historical replay uses October 25–31, 2026 and fixed five-minute checkpoints
through two hours after the first problem receipt, plus relevant version receipts.
All historical times below are New York local time.

| Corridor | Google Stay | Supplied alternatives |
|---|---|---|
| West 42nd Street / Seventh Avenue → Brooklyn Borough Hall | 2: Times Sq-42 St → Borough Hall | 3 on the same station pair; A from Port Authority to Jay St; F from Bryant Park to Jay St |
| West 42nd Street / Eighth Avenue → NYU Tandon | A: Port Authority → Jay St-MetroTech | C on the same station pair; R from Times Sq to Jay St |

Same-station service changes are ordinary Switch choices. No extra transfer
penalty is applied. The Port Authority A/C paths both use a declared 120-second
platform-access allowance because the supplementary Google coordinate walk is
zero seconds and does not measure travel to the platform. Coupled zero- and
240-second alternatives were selected from input advice, reviewed and frozen
before outcome scoring. They never enter baseline metric denominators.

## Coverage and outcome counts

The fixed grid contains 3,028 planned corridor checkpoints. Raw as-of notices
produce 1,336 broad encounters: manual review confirms 518, excludes 451, and
leaves 367 unresolved. The confirmed baseline spans 45 corridor-event pairs
and 45 unique incident IDs: 28 Times Square events and 17 Port Authority events.
Thirty-two input-selected walking variants qualify separately.

Raw-MTA Stay means the same five-minute Switch decision rule using uncorrected
feed estimates. It is not a navigation recommendation returned by MTA itself.
Each policy is evaluated using its own exact selected journey; the baseline
is not silently replaced by the fastest raw-MTA candidate.

| Comparison | Evaluated decisions | Comparable outcomes | Meaningful gains | Practical ties | Meaningful losses | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| Raw MTA Stay → incident model Switch | 21 | 10 | 1 | 9 | 0 | 11 |
| Every model Switch versus its model-selected Stay journey | 68 | 45 | 29 | 16 | 0 | 23 |
| Model versus raw-MTA chosen policy, both with definite advice | 282 | 201 | 16 | 184 | 1 | 81 |

The 23 unknown complete Switch gains include **12 missed selected Switch
journeys**, ten usable Switch journeys with unusable Stay outcomes, and one
unavailable Switch outcome. Missed trains are known feasibility failures even
when a complete replacement-journey duration cannot be calculated.

Among the 21 strict Stay-to-Switch disagreements, the 11 unknown pairs comprise
four usable raw Stay / missed model Switch, four missed raw Stay / usable model
Switch, two unavailable raw Stay / usable model Switch, and one unavailable
raw Stay / missed model Switch. These cannot be counted as successes or ties.

At the 45 input-selected primary event representatives, there are four raw-MTA
Stay / model Switch disagreements: three comparable practical ties and one
unknown. The one meaningful disagreement gain below is a later checkpoint
illustration. Repeated checkpoints are not independent experiments, and this
post-hoc search is not an untouched generalization test.

## The additional meaningful example

At **October 28, 18:50:10**, the official notice reports downtown A/C delays
while a mechanical problem on a train at Fulton St is addressed. Both lines
are affected; C is not an unaffected detour around the problem.

| Policy / journey | Prediction at decision | Final MTA-based duration proxy |
|---|---:|---:|
| Raw MTA: Stay on A | 31.59 min | 34.02 min |
| Incident model: Switch to C | 32.73 min | 28.41 min |
| Incident model's forecast for Stay A | 38.06 min | 34.02 min |

The model's predicted advantage is 5m20s and the fixed-journey outcome gain is
**5m37s**. The time-profile control still says Stay. The benefit comes from
7m29s less waiting, offset by 1m52s more riding, with the same walking duration.

The raw C departure estimate is 10.647 seconds before the assumed platform-ready
time, so raw MTA selects a later C train. The historical correction selects the
earlier C; its final departure proxy leaves 41.353 seconds of boarding slack
under the 120-second access assumption. This is evidence of a useful selection
change, not evidence that the model's absolute ETA is more accurate here.

The [endpoint audit](extra-corridor-switch-endpoint-audit.json) verifies the
selected records and finds no known earlier catchable A arrival under baseline
access. The gain is **not robust across access assumptions**: with 240 seconds,
the selected C is missed. With zero seconds, the fixed-train calculation still
shows +5m37s, but a separate near-event-supported A becomes catchable and would
beat C by 5m15s. That diagnostic is not a complete adaptive-Stay simulation.
Keep the baseline result conditional on the declared access time.

## Severe exposure

Eight confirmed checkpoints across two Times Square events have severe service
disruption, separately qualified from literal severe-delay wording:

- October 28: 2 trains run via 5 between Nevins St and 149 St-Hostos following
  an unauthorized person on the tracks at 125 St, bypassing the fixed Stay path.
- October 31: limited Manhattan–Brooklyn service and some downtown 2 trains
  terminate before Borough Hall while emergency teams respond to a person
  struck by a train at Bergen St.

Both policies recommend Switch at three of these checkpoints and abstain at
five. All three Switch gains are unknown: one selected Switch train is missed,
one Switch outcome is unavailable, and one Stay outcome is unusable. There is
no quantified successful severe-stage Switch in this supplement.

## Appendix: every comparable strict disagreement

All rows below have raw-MTA Stay and incident-profile Switch. Positive numbers
mean the model-selected journey finishes earlier. Values within ±3 minutes
remain practical ties, including the three small losses; they are not promoted
to meaningful wins to reach a requested example count.

| Historical cutoff | Corridor / Stay → Switch | Contemporaneous service problem | Raw Stay / model Switch proxy, min | Gain | Classification |
|---|---|---|---:|---:|---|
| Oct 25 12:16:57 | Port Authority → Tandon; A → C | Door problem at Port Authority; downtown A delays | 32.64 / 30.55 | +2m05s | Practical tie |
| Oct 25 12:36:57 | Port Authority → Tandon; A → C | Residual delays after the Port Authority door-problem train was removed | 27.47 / 29.39 | −1m55s | Practical tie |
| Oct 25 14:10:12 | Port Authority → Tandon; A → C | Residual delays after a door-problem train was removed at 190 St | 30.55 / 32.39 | −1m50s | Practical tie |
| Oct 25 14:15:07 | Port Authority → Tandon; A → C | Same 190 St door incident; repeated checkpoint | 25.64 / 27.47 | −1m50s | Practical tie |
| Oct 25 14:45:07 | Port Authority → Tandon; A → C | Same 190 St door incident; later checkpoint | 30.80 / 29.14 | +1m40s | Practical tie |
| Oct 28 18:50:10 | Port Authority → Tandon; A → C | Mechanical problem at Fulton St; downtown A/C delays | 34.02 / 28.41 | +5m37s | Meaningful gain; access-sensitive |
| Oct 29 15:49:28 | Times Square → Borough Hall; 2 → 3 | Residual two-way 2 delays after a person was struck at Wakefield-241 St | 26.36 / 23.65 | +2m43s | Practical tie |
| Oct 29 17:40:20 | Times Square → Borough Hall; 2 → 3 | Unauthorized person on tracks at Franklin Av; NYPD requested | 32.06 / 29.34 | +2m43s | Practical tie |
| Oct 30 15:55:37 | Times Square → Borough Hall; 2 → 3 | Activated brakes at Chambers St; downtown 2/3 delays | 34.92 / 32.59 | +2m20s | Practical tie |
| Oct 30 21:51:30 | Port Authority → Tandon; A → C | Residual two-way A delays after a switch problem near Far Rockaway-Mott Av | 35.26 / 33.51 | +1m45s | Practical tie |

All ten pairs have stable source identities and endpoint timestamps within
87 seconds of their last observation. The wider 201 paired-policy comparisons
have a maximum endpoint age of 275 seconds; no hours-stale endpoints were found.
Near-event disappearance is still an MTA-based proxy, not independent passenger
measurement or proof of a complete adaptive route outcome.

## Artifacts and reproduction

- [Frozen input cohort](extra-corridor-switch-selection-frozen.json),
  [reviewed notices](extra-corridor-switch-text-review.json), and
  [178,828-check input audit](extra-corridor-switch-input-audit.json).
- [Complete baseline and sensitivity results](extra-corridor-switch-test.json).
  Expanded evidence remains in ignored local paths identified by that report.
- [Endpoint and access sensitivity audit](extra-corridor-switch-endpoint-audit.json).
- [34,907-check outcome and aggregation audit](extra-corridor-switch-audit.json).

Nine focused tests passed; the endpoint audit passed 720 checks. The original model, training profile, thresholds and
previous frozen experiments remain unchanged. Reproduction requires the local
evidence paths recorded in the freeze:

```sh
.venv/bin/python algo/scripts/evaluate_extra_corridor_switch.py --verify-only
.venv/bin/python algo/scripts/evaluate_extra_corridor_switch.py
```

Frozen selection SHA-256:
`baf0259cd2a44263867bd2439511e9e3d48ad8c495c342dcab0bc36c8f052167`.
Result SHA-256:
`d7b11395a34ccaf379d3c02f5a05df12eca8fc85aeb5dc9b4b76937c7ef2d869`.
