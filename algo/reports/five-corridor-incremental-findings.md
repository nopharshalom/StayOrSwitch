# Incremental Switch evidence across five corridors

The completed search supplies **three meaningful baseline examples** where the
raw-MTA decision rule says Stay, the incident-profile model says Switch, and
the historical selected journeys support savings. Two are Grand Central 5-to-4
changes. The third, Port Authority A-to-C, depends on the declared station-access
assumption. A fourth positive number, Court Square's 82m50s, remains a
fixed-selected-train result and is not presented as demonstrated adaptive
Stay-on-7 savings. The evidence does not support five to ten meaningful examples
without counting small differences, unknown outcomes or repeated records.

Same-station/platform substitutions are normal valid Switch choices. They are
included without an arbitrary transfer penalty. Catchability from the street
origin is still checked for the selected train.

## Fixed comparison and coverage

Google's current default path chooses Stay; historical October 25–31, 2026 feeds
choose trains at each departure cutoff. Current Google minutes never replace
missing historical outcomes. The existing historical profiles, freshness rules,
five-minute predicted Switch threshold and ±3-minute outcome tie band are unchanged.

“Raw MTA says Stay” means the project's decision rule using uncorrected MTA
predictions, not an official MTA routing recommendation. The incremental outcome
compares the raw-MTA policy's actual selected Stay journey with the model's
actual selected Switch journey. It does not compare with an unconditional
fastest raw-MTA candidate or silently replace the baseline train.

| Corridor | Current Google-defined Stay | Confirmed checkpoints | Raw Stay / model Switch | Meaningful frozen gains / ties / unknown |
|---|---|---:|---:|---|
| Hayden LIC, 43-25 Hunter Street → NYU Tandon, 6 MetroTech Center | F, Court Sq-23 St → Jay St-MetroTech | 298 | 0 | 0 / 0 / 0 |
| East 42nd Street / Lexington Avenue → Brooklyn Borough Hall | 5, Grand Central → Borough Hall | 260 | 11 | 2 / 2 / 7 |
| Court Square Park → West 42nd Street / Seventh Avenue | 7, Court Sq → Times Sq | 56 | 2 | 1 fixed-train-only / 0 / 1 |
| West 42nd Street / Seventh Avenue → Brooklyn Borough Hall | 2, Times Sq → Borough Hall | 337 | 11 | 0 / 3 / 8 |
| West 42nd Street / Eighth Avenue → NYU Tandon | A, Port Authority → Jay St-MetroTech | 181 | 10 | 1 access-sensitive / 6 / 3 |

The first three Google paths were captured November 20 at approximately 10:54
New York time; the final two at 11:42:28. Exactly five corridors were queried.
There are 29 usable candidate paths across them, plus the explicitly unresolved
original pilot provider path. Its incomplete transfer information can prevent
a formal raw-MTA Stay decision, so the pilot's zero disagreement count is also
a comparison-coverage limitation.

The original three corridors use a denser fixed five-minute grid over the same
49 previously confirmed corridor-event pairs. The extra two have a separately
reviewed, frozen cohort of 45 pairs. Both retain relevant notice-receipt times
within two hours of the initial applicable problem. The combined **1,132
checkpoints represent 94 corridor-event pairs and 86 unique incident IDs**.
Overlapping corridors and repeated trains are not independent trials. The
earlier 322-checkpoint cohort is already included in the 614-point supplement
and is not added again. Walking variants are also excluded from baseline counts.

These are post-hoc exploratory test-week analyses. Input scope and predictions
were frozen before each new scoring pass, but earlier results from this week
were already known. No new model was trained.

## Three usable baseline illustrations

All dates and times are New York local time in 2026. Durations include declared
access, waiting, riding and egress. They use screened final MTA predictions;
they are not independently measured passenger trips. Each row represents a
different incident and selected train pair. These are later, outcome-selected
illustrations, not the input-selected primary event representatives.

| Cutoff | Corridor and Stay → Switch | Contemporaneous service problem | Raw policy Stay outcome | Model Switch outcome | Saving |
|---|---|---|---:|---:|---:|
| Oct 28, 18:50:10 | Port Authority → NYU Tandon: A → C, both Port Authority–Jay St-MetroTech, then walk | Mechanical problem on a train at Fulton St; downtown A and C delayed | 34.02 min | 28.41 min | **5m37s**, access-sensitive |
| Oct 29, 15:49:57 | Grand Central → Borough Hall: 5 → 4, same boarding/alighting stations | Downtown 2/5 delays after a signal problem at Freeman St | 29.72 min | 24.20 min | **5m31s** |
| Oct 29, 16:10:55 | Grand Central → Borough Hall: 5 → 4, same boarding/alighting stations | Both-direction 2/5 delays after EMS assistance at Jackson Av | 27.74 min | 23.64 min | **4m06s** |

**Fulton St:** raw MTA predicts Stay A at 31.59 minutes, with its best alternative
385 seconds slower. The incident profile predicts A at 38.06 and C at 32.73
minutes, recommending Switch. The time-only profile still says Stay. Historical
correction makes an earlier C train eligible; the raw forecast treats its
departure as 10.647 seconds before the assumed platform-ready time. The final
proxy instead leaves 41.353 seconds of boarding slack. Both A and C are affected;
this is not an unaffected detour around the fault.
The 337-second benefit comprises 449 seconds less waiting and 112 seconds more
riding. It demonstrates a decision benefit under the stated access assumption,
not that both corrected duration estimates are more accurate.

Port Authority's baseline adds a predeclared, shared 120-second platform-access
allowance to Google's zero-second coordinate walk, which does not measure
stairs or station entry. At 120 seconds the audit finds no earlier known
catchable A arrival. The predeclared 240-second variant misses the selected C.
At zero seconds the exact frozen train comparison still saves 337 seconds, but
an earlier near-event-supported A becomes catchable and would beat C by 315
seconds. Therefore this is a valid baseline example under the access assumption,
not a robust saving across access assumptions or an adaptive Stay strategy.

**Freeman St:** raw MTA predicts 29.89 minutes on 5 versus 27.20 on its best 4,
only 2m41s faster, so the five-minute rule says Stay. The model selects an earlier
4 and predicts 29.71 versus 23.99 minutes, crossing the threshold. The time-only
profile says Stay. The selected 4 is catchable under the recorded walk and its
historical outcome saves 5m31s.

**Jackson Av:** raw MTA already predicts a 4m57s advantage for 4, just three
seconds below the threshold. The model predicts 5m11s, selecting the same 4
train. The historical saving is 4m06s. This is a legitimate boundary crossing
in the decision rule, not evidence of a large raw-MTA ETA error.

Raw-record audits match all selected endpoints for these examples, with recent
observations. Bounded exact-line Stay searches find no earlier known catchable
5 arrival for the Grand Central examples. These searches do not establish
archive completeness. See the [three-corridor endpoint audit](incremental-switch-endpoint-audit.json)
and [extra-corridor endpoint audit](extra-corridor-switch-endpoint-audit.json).

The Court Square October 30, 05:51 case is kept in the frozen arithmetic:
7 → F gives 106.52 → 23.69 minutes. Most of Stay is waiting for one particular
7 train despite other 7 trains arriving earlier. Its 82m50s is not used as a
fourth demonstrated route-level saving. See the
[large-delay audit](google-corridors-large-delay-audit.json).

## Overall algorithm assessment

| Measure, all checkpoints | Decisions / pairs | Comparable | Meaningful gain | Practical tie | Meaningful loss | Unknown complete outcome |
|---|---:|---:|---:|---:|---:|---:|
| Model Switch versus its own selected Stay journey | 144 | 78 | 54 | 24 | 0 | 66 |
| Specifically raw-MTA Stay versus model Switch | 34 | 15 | 4 | 11 | 0 | 19 |
| Model's chosen policy journey versus raw-MTA policy's chosen journey | 471 | 317 | 28 | 286 | 3 | 154 |

These are **frozen fixed-train proxy counts**, not a passenger success rate.
The four narrow gains include Court's qualified result and Port Authority's
access-sensitive result. The 66 unknown Switch gains include **20 recommended
journeys that miss their selected train**, which are feasibility failures, not
successes or ties. The absence of measured full-duration losses among the 78
comparable Switch pairs does not negate those failures or unknown outcomes.

The matched-policy comparison also records three occasions when the model is
meaningfully worse. It can miss a useful Switch or select a slower journey.
The 28 apparent policy gains include one additional data-quality exception:
Grand Central on October 27, 16:48, model Stay 5 versus raw Switch 4, +626 seconds,
uses a boarding timestamp that persists 971 seconds past its value. Its arrival
evidence is recent, but the boarding record is weak; do not count it as a fully
supported gain. This is separate from Court's adaptive-Stay caveat.

The extra two corridors have no hours-stale selected endpoints; their maximum
endpoint ages are 258 seconds across 45 comparable model-Switch pairs and 275
seconds across 201 matched-policy pairs. Some exceed three minutes, so aggregate
proxies are weaker than the specifically audited illustration endpoints. These
post-hoc quality diagnostics qualify the frozen numbers without rewriting them.

For one input-selected representative per corridor-event, the 94-point primary
cohort gives 14 model Switch recommendations: three gains, five ties and six
unknowns. The four primary raw-Stay/model-Switch disagreements have three ties
and one unknown, **no meaningful gain**. Among 36 comparable primary policy
pairs, three favor the model and 33 tie. Later departures are relevant to the
product scenario, but they must not inflate the number of independent events.

All 17 text-qualified severe/closure checkpoints remain without a quantified
successful model Switch. Their five Switch recommendations have unknown
complete gains. The three baseline examples above concern ordinary active or
residual disruption wording; later severe wording is not backdated.

The evidence supports a small amount of incremental value from historical
correction, especially selecting an earlier train that the raw forecast treats
as uncatchable. It does not establish consistent superiority over unmodified
MTA predictions. Most matched outcomes are practically unchanged; some model
advice is worse, missing data is substantial, and access/catchability assumptions
can determine whether the benefit exists. Same-platform changes are accepted
normally throughout this assessment.

## Records and reproduction

- [Combined counts and all 34 disagreement cases](five-corridor-incremental-summary.json).
- [Independent combined aggregation audit](five-corridor-incremental-audit.json).
- [Dense original-three findings](incremental-switch-findings.md),
  [results](incremental-switch-test.json), and [audit](incremental-switch-audit.json).
- [Extra-two results](extra-corridor-switch-test.json),
  [input audit](extra-corridor-switch-input-audit.json), and
  [outcome audit](extra-corridor-switch-audit.json), with a separate
  [endpoint audit](extra-corridor-switch-endpoint-audit.json).
- [Extra provider paths and walking assumptions](../../data/docs/incremental-extra-corridors.md)
  and [historical input provenance](../../data/docs/incremental-extra-inputs.md).

The new data/replay modules pass 34 focused tests. Previous model, training
profile, source files and frozen studies remain unchanged. The aggregation
script asserts five unique corridors, unique case IDs, exact paired-outcome
arithmetic and separate incident/train-pair counts:

```sh
.venv/bin/python algo/scripts/summarize_incremental_experiment.py
```

Raw provider responses, archives and expanded intermediate records remain in
ignored local storage, referenced by paths and hashes. Reproduction from a fresh
checkout requires those referenced sources; the committed summaries and audits
are directly readable without them.
