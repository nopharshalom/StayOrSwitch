# Feed-following passenger replay

The user authorized replacing exhaustive first-actual-train ordering with a
passenger policy that chooses from the feed available at each historical time.
Default to A when the current feed makes A the earliest usable service; revise
that choice when a later feed changes the ordering or reports cancellation.
An unselected train's missing final record must not block this replay.

This version preserves the previous studies and reuses exactly their 2,306
weekday cases, 197 representatives, five corridors, full-October profile,
boarding-safe predictions and 60/180-second primary sensitivity predictions.
No retraining, regenerated predictions, case selection or parameter tuning is
performed. All November dates have already been examined; this remains a
post-hoc regression comparison. The 120-second prediction boarding margin is
unchanged and is not repeatedly imposed while a passenger is already waiting
on the platform. The daily peak-delay study remains unchanged.

## A causal feed-following policy

1. Reach the first platform after the authored access walk. At transfers, use
   the previously selected train's screened arrival plus transfer walking.
2. Read the latest fresh full-feed capture available at that time. Candidate
   identity, compatible path and raw departure forecast must come from this
   capture. Select the earliest effective raw departure, with canonical train
   identity as a stable tie-break. Do not rank by destination arrival, historical
   correction, final endpoint availability or eventual outcome.
3. A compatible train whose origin remains advertised in the fresh feed with
   an expired departure ETA is DUE_NOW. Its effective priority is the current
   clock; retain the original raw ETA in the trace. This execution rule does
   not change the conservative planning gate.
4. Between feed captures, a usable departure of the currently selected train
   at or after selection confirms boarding. If that departure is exactly at
   the next capture time, boarding precedes processing the new capture. Once
   boarded, do not retrospectively switch to a faster train.
5. If the selected departure is unknown, assume the passenger is still waiting
   strictly before the currently forecast boarding time. A new feed before
   that boundary may change the intended train without consulting final label
   quality. Record every such forecast-conditioned waiting interval. Reaching
   the boundary, including a capture exactly at it, without selected-departure
   evidence yields UNKNOWN_SELECTED_DEPARTURE. An unknown selected DUE_NOW
   service reaches this boundary immediately.
6. Mere disappearance or unresolved identity of the selected train is not
   cancellation or proven boarding. Preserve a selected-outcome unknown when
   those alternatives cannot be resolved. Explicit cancellation or a visible
   incompatible path can trigger a choice update before the ambiguous boarding
   boundary. Unselected missing outcomes never create a global ordering veto.
7. A usable selected departure earlier than selection is a missed attempt.
   Never backdate boarding or immediately choose B using this outcome fact.
   Advance to the next feed and update from the then-visible information.
8. After boarding, validate only the selected train's departure/arrival and
   continue through the fixed route. A missing selected arrival remains unknown;
   do not replace it with a better-recorded train. No route changes or hindsight
   fastest-destination searches are allowed.

Use the same 120-second feed continuity/freshness scope, strict 180-second
endpoint-age screen and 7,200-second elapsed horizon as the preceding study.
Do not require a fresh capture after an already evidenced boarding merely to
validate a later unrelated refresh. A feed gap while still waiting is explicit
uncertainty. Horizon limits are censored, not invented travel times.

## Assumptions and reporting

The archive consists of sampled historical MTA forecasts and screened final
prediction proxies. It is not an independent passenger movement log. Choices
made while a temporarily intended train lacks departure evidence are allowed
under the declared forecast-conditioned waiting assumption. Report this
condition separately for completed routes and comparable pairs; do not
silently describe these paths as independently physically verified.

Report all cases, representatives, severe cases, each corridor and November
16–18. Keep meaningful gains/losses outside the existing plus/minus three-minute
tie band, raw-MTA versus model comparisons, narrow raw-Stay/model-Switch cases,
and explicit unknown reasons. Compare the new executor with the preceding
strict executor on the exact same repaired recommendations (339 Switch cases),
and execute the original recommendations under this same new policy as a
separate matched comparison. Preserve the unchanged boarding diagnostics.

Freeze this protocol, configuration, executable producers, reused forecasts
and source hashes before scoring. Verify current-capture-only choices,
updates before boarding, final-data isolation, due-now behavior, selected
missing outcomes, and unchanged cohort/advice. Independently audit result
counts and a bounded set of gains, losses, recovered and unknown examples.

Data access and feed views live under `data/`; execution and evaluation live
under `algo/`. Preserve original files with
`data/manifests/november-feed-replay-preservation.json`. A separate index may
reuse the verified v2 event archive without altering its bytes or its reports.
