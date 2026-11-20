# November boarding and route-execution repair

The user authorized implementation after reviewing the November weekday
limitations. This is a new version and a post-hoc regression comparison on
already examined November data, not an untouched generalization test. The
full-October model is not retrained. Preserve all earlier code, models,
predictions, cohorts and reports; publish new outputs separately.

## Fixed comparison population

Use exactly the existing 2,306 input-qualified weekday checkpoints and 197
earliest corridor/publisher-family representatives from
`algo/reports/november-weekday-selection-frozen.json`. Retain all five corridors,
the 29 supplied paths, existing Google Stay choices, incident qualifications,
severe evidence bases, walking assumptions, and November 16–18 subgroup.
The dates remain November 2–6, 9–13 and 16–18, 2026, New York time. Do not
select cases using successful recovered outcomes or tune on resulting gains.

## Prediction repair

- Keep expected ETA correction separate from boarding feasibility.
- The boarding gate uses the earlier of raw and historically corrected
  departure. Positive historical delay therefore cannot make an otherwise
  uncatchable train eligible; negative correction can tighten the gate.
- Require a 120-second margin after platform readiness. Sensitivity evaluates
  60 and 180 seconds on the same 197 primary cases. These are declared initial
  settings, not claimed calibrated optima.
- Initial readiness is departure cutoff plus access walking. Transfer
  readiness uses the later of the selected previous leg's raw and corrected
  arrival, plus transfer walking. Keep expected-time arithmetic separately;
  the feasibility buffer is not an extra cost added to travel duration.
- Apply identical feasibility logic to uncorrected MTA, time-only profiles,
  and incident profiles. Keep the 300-second predicted Switch threshold and
  the 180-second practical outcome tie band.
- Preserve all existing identity, feed freshness, service conflict and
  chronology checks. Same-platform substitutions remain ordinary valid
  alternatives with their authored walking durations.

## Route execution with archived evidence

Freeze the initial route recommendation before reading outcomes. Execute its
fixed sequence of allowed services, directions, boarding/alighting stops and
transfers. At each actual platform-ready time, board the first compatible
actually catchable service established by the archive, then follow its
screened departure and arrival evidence. Continue to a later train when the
initially predicted train is missed. Do not choose a train by its eventual
destination arrival or change the route retrospectively to improve savings.

The archive must establish compatible service at the relevant historical time,
not infer it only from a later corrected path. Unknown potentially earlier
trains, identity conflicts, unresolved stop changes and missing departure
evidence cannot be silently skipped in favor of a complete later record.
Select the earliest eligible departure before inspecting whether its final
destination label is usable. Missing arrival evidence for that train remains
unknown. Apply the existing confirmation and 180-second endpoint-age guards;
disappearance alone proves neither arrival nor cancellation.

Fix the candidate observation window at 120 seconds before the original
decision cutoff through the execution horizon. Do not reset that window at
each later platform-ready time. Carry unresolved origin candidates forward
despite omission from a newer feed, unless usable earlier departure/downstream
arrival or explicit compatible-path exclusion resolves them. Events outside
this declared observation window are outside scope, not proven departed.
Thus the replay identifies the first evidenced compatible train within its
archive observation scope, not an exhaustive independent physical movement log.

Use a maximum 120-second gap between relevant usable archive feed captures as
an explicit continuity assumption. This is separate from the 120-second
prediction boarding margin. The maximum execution horizon is 7,200 seconds
from the original departure cutoff, including walks and transfers. A horizon
limit is censored evidence, not an invented two-hour trip or an automatic loss.
Known physical movement remains inferred from final MTA prediction proxies;
the archive is not an independent passenger or vehicle-location measurement.

## Isolate evaluator and algorithm effects

Execute both the old frozen recommendations and new recommendations with the
same new route-execution policy and evidence. Cache shared case/path outcomes
across models; the execution policy itself is independent of forecast mode.
Keep the old exact-selected-train diagnostic alongside route execution so
eventual completion does not erase an initial boarding failure.

Report all checkpoints, primary representatives, qualified severe cases,
each corridor, and November 16–18. Include Switch gain/tie/loss/unknown counts,
unknown reason categories, paired model-versus-MTA and incident-versus-time
results, raw-Stay/model-Switch cases, and the matched old/new comparison.
Report the originally selected train's boarding feasibility separately from
complete route travel-time savings. Repeated checkpoints are not independent
incidents. Keep the existing peak-delay tables intact as the prior descriptive
study; this repair targets Stay/Switch execution and does not silently redefine
those fixed-train ETA residuals.

## Verification and reproducibility

Data reconstruction and evidence indexing belong under `data/`. Prediction,
route execution and benchmark code belong under `algo/`. Bind source, policy,
model, cohort and implementation hashes in a new forecast freeze before
scoring. Add focused tests for boarding gates, transfer readiness, chronology,
missed-train recovery, earlier unknown trains, destination-label failures,
coverage gaps and horizon censoring. Independently recompute result counts and
check a balanced sample of gains, losses, recovered and unresolved cases.
Preserve original artifacts with `data/manifests/november-repair-preservation.json`.
