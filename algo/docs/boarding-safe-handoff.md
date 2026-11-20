# Boarding-safe algorithm handoff

The repaired predictor is `stayorswitch.boarding_safe`. It compares routes
supplied by Google or another provider for a passenger who has not boarded and
is leaving now. It does not generate paths. The original `stayorswitch.severe`
predictor and its frozen experiments remain unchanged.

## Runnable entrypoint

From the repository root, this example uses the existing research route
configuration and locally prepared November captures:

```sh
PYTHONPATH=algo:. .venv/bin/python algo/scripts/run_boarding_safe.py \
  --config data/config/october.json \
  --snapshots data/processed/november-2026/2026-11-18.snapshots.jsonl.gz \
              data/processed/november-2026/2026-11-18.alerts.jsonl.gz \
  --cutoff 2026-11-18T08:00:00-05:00 \
  --current-route-id f_direct \
  --mode incident_profile \
  --boarding-margin-seconds 120 \
  --output algo/local/boarding-safe-example.json \
  --json
```

Replace the research configuration with the user's provider routes and actual
walking estimates in an application. The example is a forecast query at the
specified historical cutoff, not a request to evaluate later travel outcomes.

The CLI requires `--config`, `--snapshots`, `--cutoff`, and an explicit
`--current-route-id`. It rejects a Stay identifier absent from the supplied
configuration. It never selects a default Stay on the user's behalf.

Defaults are:

| Setting | Value |
|---|---|
| Profile | `data/artifacts/october-2026-profiles-full-train.json.gz` |
| Modes | `all`: raw MTA, time profile, incident profile |
| Boarding margin | 120 seconds |
| Predicted Switch advantage | 300 seconds, unless supplied in the configuration |
| Service trigger | All service contexts with verified applicable evidence |
| Severe-only trigger | Opt in with `--severe-only` |

`--mode mta` does not load a training artifact. Other modes verify the profile's
content seal and reject a prediction cutoff preceding its training boundary.
The full-October default is therefore used only at or after November 1, 2026,
00:00 in New York. Passing `--profiles` chooses another frozen training artifact.

The local feed reader preserves only captures received by the cutoff and retains
the supplied earlier alert versions. Include relevant alert history as well as
train captures. Future captures present in the archive cannot enter inference.
A stale or failed latest capture remains unavailable rather than reviving an
older successful one. This CLI makes no external API calls and needs no API key.

## Provider configuration

The configuration is a JSON object with a `routes` list. Every route requires
a stable unique `id`, access/egress walking seconds, one walking duration per
transfer, and subway legs with explicit feed, line, and directional stop IDs.
The template schema is described in the preserved
[supplied-route interface](severe-comparison.md#python-integration).

Optional configuration fields are `train_max_age_seconds` (default 180),
`alerts_max_age_seconds` (300), `switch_margin_seconds` (300), and
`walking_policy` for the provenance of the walking estimates.

An unresolved provider path belongs in `unavailable_candidates`, for example:

```json
{
  "id": "provider-route-with-missing-transfer",
  "reason_codes": ["MISSING_TRANSFER_WALK"]
}
```

The CLI retains those paths as unavailable alternatives. They prevent a false
claim that all alternatives were assessed; they are never treated as slower
routes or silently dropped. At least one complete route template is required.
Duplicate route identifiers and incomplete walking fields in a purportedly
complete template are input errors.

## Python entrypoints

```python
from data.delay_profiles import IncidentIndex, ProfileEstimator
from stayorswitch.boarding_safe import evaluate_modes

profiles = ProfileEstimator("data/artifacts/october-2026-profiles-full-train.json.gz")
incidents = IncidentIndex(asof_alert_snapshots, max_age_seconds=300)
report = evaluate_modes(
    asof_snapshots,
    supplied_complete_routes,
    cutoff,
    current_route_id,
    estimator=profiles,
    incident_index=incidents,
    boarding_margin_seconds=120,
    switch_margin_seconds=300,
    require_severe=False,
)
```

`predict_routes(...)` produces one forecast mode. The unchanged `decide(...)`
compares it with the explicit Stay. `evaluate_modes(...)` runs all three modes.
Pass `require_severe=False` explicitly to match the repair benchmark and CLI;
the low-level decision helpers retain the original severe-only default.
Direct Python callers must enforce profile training-date suitability and keep
unresolved provider candidates visible when assembling the decision input.

## Boarding and ETA are separate

The boarding gate uses the earlier of raw and corrected departure. Positive
historical departure delay can never make an otherwise uncatchable train
eligible. First-leg readiness is departure-now plus access walking. Transfer
readiness uses the later of the previous leg's raw/corrected arrival plus
the supplied transfer walk. A candidate needs the configured extra margin
beyond this conservative readiness.

Expected departure and arrival corrections still determine ETA ranking,
waiting, and riding components. The boarding margin is not added to elapsed
travel time and does not invent a same-platform transfer penalty. Each selected
or timing-rejected leg exposes a `boarding_gate` record with conservative
readiness, expected readiness, gate departure, remaining slack and required
margin. The report also preserves historical support and fallback information.

Use `strict_decision` for advice. `conditional_timing_decision` is a timing-only
diagnostic when service evidence is insufficient. Unknown does not mean Stay.
The 120-second margin is an initial evaluated policy, not a calibrated guarantee
that every recommended train can be boarded.

## Historical execution is an evaluation component

The live predictor takes no outcome-label or future-feed argument. Its output
is an ETA and recommendation, not a measured actual journey. The CLI explicitly
reports `prediction_uses_outcomes=false` and `actual_travel_time_computed=false`.

The separate [route executor](../stayorswitch/route_execution.py) advances through
archived evidence after a frozen route decision to assess first compatible
boarding, later waits and transfers. The
[repair benchmark](../scripts/evaluate_november_repair.py) compares those outcomes
with the retained exact-selected-train diagnostics. It can account for waiting
after a missed initial prediction; it does not feed later evidence back into
the original recommendation or choose a future train by its eventual fastest
destination arrival. Incomplete evidence remains explicit. These historical
outcomes are screened final-MTA proxies plus the declared walking assumptions,
not independently observed passenger journeys.

The protocol and comparison scope are in the
[November repair plan](november-repair-plan.md).
