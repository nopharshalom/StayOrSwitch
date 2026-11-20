# Three Google-defined Stay corridors: findings and evidence limits

The historical replay supports a substantial F-to-G saving for the LIC-to-Tandon
pilot. Grand Central has smaller, boarding-sensitive 5-to-4 substitutions.
Court Square's largest difference is a fixed-selected-train comparison and does
not establish the saving against a passenger who stays on the 7 and takes an
earlier available train. No successful Switch during explicitly severe-delay
wording has a quantified, comparable outcome in this cohort.

These are exploratory October 25–31, 2026 results using screened final MTA
predictions and declared walking times. They are not independently measured
passenger journeys. All dates and times below are New York local time.

## What Google supplies

Google was queried on November 20, 2026 at approximately 10:54. Its uniquely
labeled default route determines the exact Stay line and stop sequence.
Neither its current duration nor its current train is used as an October
outcome. The selected path is not claimed to have been historically fastest.

| Corridor | Google-defined Stay | Current provider-reported duration | Query-clock duration to arrival plus egress |
|---|---|---:|---:|
| Hayden LIC, 43-25 Hunter Street → NYU Tandon, 6 MetroTech Center | F: Court Sq-23 St → Jay St-MetroTech | 36m22s | 37.90 min |
| East 42nd Street / Lexington Avenue → Brooklyn Borough Hall | 5: Grand Central → Borough Hall | 23m57s | 31.60 min |
| Court Square Park → West 42nd Street / Seventh Avenue | 7: Court Sq → Times Sq | 14m38s | 18.35 min |

Google's raw duration differs from departure-at-query-clock duration; both are
retained in the [capture record](../../data/docs/google-corridors.md). Historical
predictions and outcomes instead start at the same historical decision time,
including access, waiting, riding, transfers and egress.

The frozen configuration has 22 usable paths: 11 pilot, eight Grand Central and
three Court Square paths. They include F, G, R, E-to-A/C, 7-to-4/5, 7-to-2/3,
N/W-to-R, 7-to-F, 6-to-R and direct walking-to-station alternatives as applicable.
One additional Google E-to-A path remains explicitly unavailable because its
transfer walk cannot be resolved. It is distinct from the usable research
E-to-A path via Port Authority. All alternatives, including unavailable ones,
remain in the [full comparisons](google-corridors-test.md).

## Cohort and recommendation counts

The [protocol](../docs/google-corridor-experiment.md) fixes current Google paths,
candidate routes and historical notice checkpoints before outcome scoring.
It retains 49 corridor-event representatives and 322 confirmed checkpoints.
Primary representatives are selected from inputs, not from eventual gains.
Later checkpoints repeat incidents and are not 322 independent experiments.
The test week had already been explored in previous studies.

All results in this table use the unchanged incident-profile predictor and its
formal recommendation, with at least five minutes of predicted savings required
for Switch. Outcome differences within ±3 minutes are practical ties.

| Cohort / corridor | Cases | Switch advice | Comparable Switch pairs | Meaningful gains | Practical ties | Meaningful losses | Unknown complete gain |
|---|---:|---:|---:|---:|---:|---:|---:|
| Primary event representatives | 49 | 4 | 1 | 1 | 0 | 0 | 3 |
| All checkpoints: LIC → Tandon | 158 | 19 | 10 | 6 | 4 | 0 | 9 |
| All checkpoints: Grand Central → Borough Hall | 132 | 23 | 4 | 4 | 0 | 0 | 19 |
| All checkpoints: Court Square → Times Square | 32 | 2 | 1 | 1 | 0 | 0 | 1 |
| All checkpoints combined | 322 | 44 | 15 | 11 | 4 | 0 | 29 |

The Court Square gain in this unchanged table is strictly a fixed-train result;
see its qualification below. The table does not establish a general Switch
success rate. Of 44 recommendations, 29 have unknown complete gains. Those
unknowns include five recommended journeys whose selected boarding or transfer
was missed, as well as absent or unreliable endpoint labels. A known missed
train is a feasibility failure even when a complete replacement journey cannot
be scored. It is not a success, a tie, or merely a missing record.

The 207 formal abstentions include 104 cases with an unassessed alternative,
60 with unavailable Stay timing, and 43 without verified current service
evidence. In particular, the unresolved provider E-to-A candidate can prevent
a formal Stay decision when no known alternative clears the Switch threshold.
Abstentions therefore reflect data/configuration coverage as well as advice
rules. Counterfactual fastest-alternative outcomes in the full report are kept
separate from actual recommendations.

## LIC → Tandon: strongest primary illustration

At **October 28, 21:27:45**, an applicable southbound F delay notice was active.
The incident-profile algorithm recommended switching from F to G.

| Journey | Predicted duration at the decision | Final MTA-based duration proxy |
|---|---:|---:|
| Stay: F, Court Sq-23 St → Jay St-MetroTech | 59.33 min | 62.06 min |
| Switch: G, Court Sq → Hoyt-Schermerhorn Sts | 37.97 min | 38.47 min |

The proxy saving is **23m35s**. This is the input-selected primary
representative, not a later checkpoint chosen for its outcome. All eight
predeclared walking variants retain Switch; their comparable savings range
from **21m35s to 27m24s**, changing one walking component at a time by two
minutes. This is sensitivity evidence, not a simultaneous worst-case bound.

The [raw-record audit](google-corridors-primary-example-audit.json) confirms
both train identities, endpoint values and near-event stop disappearance.
A bounded search found no known usable exact-line F train arriving earlier
than the selected Stay train, but does not prove archive completeness. The
notice names a cause farther south at Avenue X; the applicable header describes
directional F delays, not an obstruction physically between Court Square and Jay.

Raw MTA and the time-profile control also recommend G here and obtain the same
outcome proxy. This case supports the usefulness of switching, without proving
incremental benefit from the historical correction.

## Grand Central → Borough Hall: useful but fragile service substitutions

At **October 26, 10:04:28**, the algorithm recommends **5 → 4**:

| Journey | Predicted duration | Final MTA-based duration proxy |
|---|---:|---:|
| Stay: 5 | 30.38 min | 29.31 min |
| Switch: 4 | 25.28 min | 21.99 min |

The proxy saving is **7m19s**, but the selected 4 train has only **18.41 seconds**
of boarding slack after the configured access walk. This is a later checkpoint
illustration, not a primary representative. The official EMS notice affects
both downtown 4 and 5; the 4 is not an unaffected route around the problem.
Both raw MTA and the time-profile control also recommend this change.

All four comparable Grand Central recommendations change between the same
boarding/alighting stations. Their savings and Switch boarding slack are:

| Historical cutoff | Proxy saving | Boarding slack after assumed walk |
|---|---:|---:|
| October 26, 10:04:28 | 7m19s | 18.41 s |
| October 26, 15:31:45 | 5m53s | 76.45 s |
| October 29, 15:49:57 | 5m31s | 37.20 s |
| October 29, 19:07:37 | 3m26s | 35.29 s |

Adding two minutes to access would miss each originally selected 4 train under
the proxy. This diagnostic does not determine what a newly planned replacement
train would achieve; no such replacement-policy replay was run. These later
checkpoints have no predeclared walking-variant replay. The corridor produces
17 same-station substitutions and six other-path recommendations overall, but
no comparable geographic-detour win. See the
[endpoint and boarding audit](google-corridors-scorable-switch-endpoint-audit.json).

## Court Square → Times Square: fixed-train gain, adaptive Stay unresolved

At **October 30, 05:51:23**, the model recommends **7 → F** during an ordinary
delay notice about an unauthorized person near 46 St. The severe wording arrives
later, at approximately 07:19, and cannot describe the 05:51 decision.

| Journey | Predicted duration | Final MTA-based duration proxy |
|---|---:|---:|
| Stay: originally selected 7 train | 23.38 min | 106.52 min |
| Switch: selected F train | 15.22 min | 23.69 min |
| Other candidate: E | See full record | 23.24 min |

The **82m50s** difference is arithmetically supported for the exact selected
trains. However, Stay includes **92.54 minutes waiting for that particular 7**.
A separate, near-event-supported 7 train would arrive earlier, with a 61.69-minute
journey from the same cutoff. That diagnostic is enough to reject an
interpretation that all passengers remaining on the 7 would wait for the
original train. It is not enough to establish the earliest achievable adaptive
Stay journey or its savings.

The [raw large-delay audit](google-corridors-large-delay-audit.json) preserves
the original result and documents this limitation. Some apparently earlier
alternative 7 labels persist for almost 22 hours before stop removal, exposing
a gap in the existing outcome screen. Those unreliable alternatives are not
used to replace the baseline. All 15 comparable strict Switch pairs in the
frozen cohort use endpoint timestamps within 92 seconds of their last
observation; none uses these hours-stale endpoints. Near-event evidence still
does not turn a fixed-train strategy into an adaptive route strategy.

The raw-MTA policy says Stay here because its predicted difference is below
five minutes; the historical profiles recommend F. However, simply taking the
fastest raw-MTA candidate selects E, whose outcome is 27 seconds faster than F,
a practical tie. This example does not establish historical-model superiority.
It is also a later checkpoint without a predeclared walking-variant replay.

## Severe conditions and remaining model limitations

All 49 primary representatives have ordinary disruption wording. Of all 322
checkpoints, 318 are ordinary and four have text-qualified severe/closure
exposure: three literal severe-delay checkpoints on the 7 and one no-service /
reroute checkpoint on the Grand Central corridor. None supplies a quantified
successful Switch under severe exposure.

At the Grand Central no-service checkpoint on October 28, 07:34, the unchanged
algorithm recommends 5 → 4 even though the 4 is also affected; both outcomes
are unusable. This is a preserved limitation of its disruption interpretation,
not a validated route around a closure. Multi-clause notice parsing and shared
disruption exposure need improvement before relying on such advice.

The raw-MTA control makes 55 Switch recommendations across all checkpoints:
21 comparable pairs, comprising 19 gains and two ties, with 34 unknowns.
Different recommendation and coverage sets prevent concluding from these
counts that either mode is globally better. The current experiment establishes
some useful switching opportunities and identifies concrete weaknesses; it
does not establish reliable severe-incident advice or a citywide success rate.

## Artifacts and validation

- [Full per-route tables](google-corridors-test.md) and
  [machine-readable results](google-corridors-test.json).
- [Selection freeze](google-corridors-selection-frozen.json),
  [notice review](google-corridors-text-review.json), and
  [as-of notice membership audit](google-corridors-asof-membership-audit.json).
- [Data provenance](../../data/docs/google-corridor-inputs.md),
  [input audit](google-corridors-input-audit.json),
  [outcome audit](google-corridors-outcome-audit.json), and
  [summary audit](google-corridors-summary-audit.json).

The new data and replay modules passed 52 focused tests. Independent audits
passed 425,477 input checks, 262,095 outcome checks and 5,579 aggregation checks.
Raw archives, provider payloads and expanded intermediate artifacts remain
local, referenced by paths and hashes. The original predictor, training profile
and previous experiments remain unchanged.

This findings appendix qualifies, without rewriting, frozen result SHA-256
`d2307886145dfccdd9d28d9d98695cbee383c1bb3d9c3ec0b11e2cbb10ea323e`
and selection SHA-256
`c2ddb1e228b830bb9beaca4ceae25ebe8a4a6375f68e5b78107bfbbdc9e63b28`.
With the referenced local evidence present, the runner's `--freeze-only` mode
verifies selection; its default mode reproduces scoring:

```sh
.venv/bin/python algo/scripts/evaluate_google_corridors.py --freeze-only
.venv/bin/python algo/scripts/evaluate_google_corridors.py
```
