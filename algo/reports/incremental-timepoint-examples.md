# Five departure-time examples of incremental Switch advice

The user explicitly allows the same selected train pair at different departure
times to appear as multiple examples. Under that convention, **five baseline
illustrations** satisfy raw-MTA Stay, incident-profile Switch and more than
three minutes of historical proxy savings, without a known earlier catchable
exact-line Stay arrival under the declared access assumptions.

These are five departure times from **three service problems and three train
pairs**, across two of the five tested corridors. Repeated trains and occasional
reused feed captures are intentional and labeled below. Same-platform service
changes count as normal Switch choices without an arbitrary transfer penalty.

## Cases

All timestamps are New York local time in October 2026. “Raw MTA Stay” means
unmodified feed predictions evaluated with the same five-minute Switch threshold
as the historical model; it is not an official MTA navigation recommendation.
All five rows have raw-policy Stay and model-policy Switch. Durations compare
each policy's actually selected historical train sequence, including declared
walking, waiting, riding and egress.

| Case | Departure | Corridor | Stay route | Switch route | Applicable service problem | Historical Stay / Switch duration | Saving | Train-pair group |
|---|---|---|---|---|---|---|---|---|
| 1 | Oct 28, 18:49:40 | Port Authority, W42 St/8 Ave → NYU Tandon, 6 MetroTech | A: Port Authority → Jay St-MetroTech, then walk | C: same boarding/alighting stations, then walk | Mechanical problem on a train at Fulton St; downtown A/C delays | 34.52 / 28.91 min | **5m37s** | P |
| 2 | Oct 28, 18:50:10 | Port Authority, W42 St/8 Ave → NYU Tandon, 6 MetroTech | A: Port Authority → Jay St-MetroTech, then walk | C: same boarding/alighting stations, then walk | Same Fulton St mechanical problem | 34.02 / 28.41 min | **5m37s** | P |
| 3 | Oct 29, 15:49:57 | Grand Central, E42 St/Lexington → Brooklyn Borough Hall | 5: Grand Central → Borough Hall | 4: same boarding/alighting stations | Downtown 2/5 delays after a signal problem at Freeman St | 29.72 / 24.20 min | **5m31s** | S |
| 4 | Oct 29, 16:10:25 | Grand Central, E42 St/Lexington → Brooklyn Borough Hall | 5: Grand Central → Borough Hall | 4: same boarding/alighting stations | Both-direction 2/5 delays after EMS assistance at Jackson Av | 28.24 / 24.14 min | **4m06s** | M |
| 5 | Oct 29, 16:10:55 | Grand Central, E42 St/Lexington → Brooklyn Borough Hall | 5: Grand Central → Borough Hall | 4: same boarding/alighting stations | Same Jackson Av EMS incident | 27.74 / 23.64 min | **4m06s** | M |

Cases 1–2 use the same A/C pair; cases 4–5 use the same 5/4 pair. Cases 4–5
also reuse the same selected feed capture. Their departure times differ, so
walking readiness and remaining journey time differ, but they are not new
independent train observations.

Case 1 is a threshold crossing: raw MTA predicts A at 32.09 and C at 27.59
minutes, a 4m30s advantage, while the model predicts 38.56 and 33.34 minutes,
a 5m13s advantage. Both modes consider the same C train. In case 2, raw MTA
treats that earlier C as already uncatchable and considers a later C instead;
historical correction makes the earlier train eligible. Both cases save waiting
time despite C having a longer ride. Both A and C are affected by the notice;
C is not an unaffected detour.

Case 3 also selects an earlier 4 than the raw forecast would consider catchable.
For cases 4–5, raw MTA already predicts a 4m57s advantage, only three seconds
below the five-minute threshold; the model predicts approximately 5m11s. These
two are valid threshold-boundary examples, not evidence of a large raw ETA error.

## Walking and outcome qualifications

Outcomes are screened final MTA predictions with declared walking times, not
independently measured passenger trips. The raw-record audit verifies all used
endpoint timestamps and identities; endpoint-to-last-observation ages are
19–92 seconds, with stop-removal gaps no larger than 11 seconds.

Port Authority uses a shared, explicitly authored 120-second street-to-platform
allowance for A and C. It is separate from Google's zero-second walk between
colocated street/station coordinates. At that baseline, cases 1–2 leave 71.35
and 41.35 seconds to catch the selected C, and no earlier known catchable A is
found. Increasing access to four minutes would miss that C. With zero access,
an earlier A becomes catchable. These are access-sensitive baseline examples,
not a claim that switching is best for every possible station-entry time.

The same record search finds no earlier known catchable 5 arrival for cases
3–5. This is a bounded archive check, not a completeness proof. Same-platform
switching itself is accepted; the access assumption concerns reaching the
platform from the stated street origin.

Three other Port departures, at 18:48:10, 18:48:40 and 18:49:10, also produce
a fixed-selected-train arithmetic gain of 337 seconds. However, an earlier A
departing at 18:51:11 is catchable under the 120-second assumption and would
beat C by 315 seconds. Those three remain in the machine-readable record with
this qualification and are not used in the five-row table. The earlier A has
two normalized aliases for one physical train, not two independent trains.

The remaining raw-Stay/model-Switch point, Grand Central on October 29 at
16:20:25, recommends 7→2 but misses its selected 7 by 5.647 seconds under the
proxy. Its complete gain is unknown; it is a feasibility failure, not a success.

## How the additional examples were obtained

This is an explicitly post-hoc illustration exercise targeting the three
already positive event families. It uses a fixed 30-second departure grid from
the first applicable problem receipt through 120 minutes, plus prior receipt
checkpoints. The grid produces 729 planned and 266 qualified event/time pairs.
Exact previously reviewed notice scopes, full parent-study source projections,
candidate paths, model and thresholds are unchanged. All 32 overlapping prior
checkpoints reproduce their original predictions.

The new input predictions were frozen before opening their outcome labels.
There are nine raw-Stay/model-Switch points: eight numerical fixed-train gains
and one missed journey. The earlier-A audit qualifies three of the eight gains,
leaving the five baseline illustrations above. No additional corridor or
further grid refinement was introduced. This targeted exercise must not be
pooled into overall algorithm performance or presented as eight independent
successful incidents.

## Overall assessment remains based on five corridors

The separate [five-corridor evaluation](five-corridor-incremental-findings.md)
retains 1,132 checkpoints, 94 corridor-event representatives and 86 unique
incident IDs. The later illustrative refinement does not change its denominators.

| Existing evaluation measure | Total decisions/pairs | Meaningful gains | Practical ties | Meaningful losses | Unknown complete outcome |
|---|---:|---:|---:|---:|---:|
| Model Switch versus its selected Stay | 144 | 54 | 24 | 0 | 66 |
| Raw-MTA Stay versus model Switch | 34 | 4 | 11 | 0 | 19 |
| Model policy versus raw-MTA policy, both giving concrete advice | 471 | 28 | 286 | 3 | 154 |

These remain fixed-train proxy counts. The 66 unknown Switch gains include 20
missed selected journeys. The narrow four numerical gains include the Court
Square fixed-train outlier and Port's access-sensitive example. The broader
28 policy gains also include the separately documented 971-second stale
boarding-label exception. The detailed findings preserve those qualifications;
neither observed gains nor the absence of complete-duration Switch losses
establish a general success rate. No quantified successful severe-stage Switch
has been established.

The model demonstrates some additional useful departure-time choices, but most
matched outcomes are practically unchanged, some model choices are worse,
and many outcomes cannot be fully verified. The five examples meet the user's
allowed repeat convention; the strength of the evidence still comes from three
underlying events, not five independent service problems.

## Evidence

- [Refinement protocol](incremental-example-refinement-protocol.md).
- [Frozen selection](incremental-example-refinement-selection-frozen.json).
- [All nine policy disagreements and train/feed repeat groups](incremental-example-refinement-test.json).
- [Independent refinement audit](incremental-example-refinement-audit.json).
- [Raw endpoint and earlier-Stay audit](incremental-example-refinement-endpoint-audit.json).
- [Unchanged five-corridor counts](five-corridor-incremental-summary.json).

The runner is `algo/scripts/refine_incremental_examples.py`. Expanded inputs
and scored evidence remain in ignored local storage with paths and hashes in
the committed records. Original frozen studies and trained profiles are unchanged.
