# Time-profile and severe-service comparison

`stayorswitch.severe` estimates the destination ETA of supplied subway journeys
and compares them with an explicit current journey. It does not generate paths.
The initial passenger has not boarded and departs at the information cutoff.
All code consumes local normalized inputs; it neither calls Google nor reads
outcome labels. The October research configuration supplies 11 variants in
seven families. These are research templates, not archived Google itineraries.

## Python integration

Run with the repository root and `algo/` on `PYTHONPATH`:

```python
from data.delay_profiles import IncidentIndex, ProfileEstimator
from stayorswitch.severe import evaluate_modes

profiles = ProfileEstimator("data/processed/october/profiles-train.json.gz")
incidents = IncidentIndex(alert_snapshots, max_age_seconds=300)
report = evaluate_modes(
    snapshots, supplied_routes, cutoff, current_route_id,
    estimator=profiles, incident_index=incidents,
    switch_margin_seconds=300,
)
```

`cutoff` is Unix UTC seconds or a timezone-aware ISO timestamp. The caller
preserves the user's current itinerary ID. Historical replay alone selects
the fastest same-cutoff MTA template as its reference. A missing current route
returns `NOT_APPLICABLE`; the algorithm never silently invents a reference.
An `IncidentIndex` must include available alert observations, including empty
successful captures and failed captures. A missing index is unknown evidence.
Only observations received by the cutoff may affect a prediction.

Each supplied route has:

```json
{
  "id": "provider-stable-id",
  "family": "F_DIRECT",
  "access_walk_seconds": 300,
  "egress_walk_seconds": 300,
  "transfer_walk_seconds": [],
  "legs": [{
    "route_id": "F",
    "route_ids": ["F", "FX"],
    "feed_id": "bdfm",
    "from_stop_id": "F09S",
    "to_stop_id": "A41S"
  }]
}
```

Live callers must resolve provider station metadata to unambiguous directional
MTA stop IDs before constructing these inputs, using the retained matching
adapter. Preserve provider access, transfer, and final walking durations.
Require one explicit transfer duration between every pair of riding legs.
No arbitrary walking, transfer, or detour penalty is added. The October
configuration's authored walking durations need the documented sensitivity
analysis; they are not measured historical walks or verified entrances.

`predict_routes(...)` returns one mode without making a decision.
`decide(prediction, current_route_id)` attaches strict and conditional decisions.
`evaluate_modes(...)` runs all three modes with identical source inputs:

| Mode | Endpoint predictions |
|---|---|
| `mta` | Unmodified current MTA departure and arrival predictions |
| `time_profile` | MTA plus supported historical means by time, horizon, and segment |
| `incident_profile` | MTA plus supported as-of incident-conditioned means, with disclosed backoff |

Profiles group local time and day type in `data/`. A correction is the remaining
error of the current MTA endpoint, not an extra copy of all incident delay.
Departure and arrival are corrected separately. Waiting is corrected departure
minus platform-ready time; riding is corrected arrival minus corrected
departure. Destination ETA is the final corrected arrival plus final walking.
An arrival residual is never added again as a separate ride delay.

## Catchability and evidence

The latest received capture for each train feed must be fresh. A newer missing
capture does not fall back to an older successful one. Each selected train
requires a unique service-qualified identity, true departure prediction, and
an ordered, usable boarding/alighting pair in its actual stop updates.
Express aliases remain eligible only when those stops actually occur in order.
Canceled, duplicate, stale, expired, missing, and nonmonotonic candidates are
rejected with reasons. A positive correction cannot resurrect a baseline
departure already in the past. An earlier corrected departure can make a train
uncatchable; an earlier corrected arrival cannot precede its departure.

The observed encoded MTA trip ID, service date, actual route, and feed identify
one physical service run independently of normalized start-time jitter.
Multiple aliases for that run in the same capture are rejected as
`SIMULTANEOUS_CANONICAL_TRIP_ALIASES`, even when one alias lacks a requested
endpoint. A start-time revision across separate captures remains usable.
Selected train provenance retains its original normalized ID; this identity
check reads observation metadata only and never opens an outcome label.

Among catchable trains, select the earliest predicted arrival, allowing
overtaking. Add transfer walking, then select the downstream train using that
new platform-ready time and the same original information cutoff. No future
feed is fetched for a later leg. Fresh structured `NO_SERVICE` evidence that
matches the actual traversed segment rejects a conflicting train. Explicit
route-wide text such as "G trains are not running" also rejects an affected
train when the incident index establishes fresh, unambiguous applicability.
Text naming an unmapped section, such as "No G trains between X and Y," remains
ambiguous: it withholds strict advice while retaining conditional timing. The
algorithm does not invent station boundaries from free text. Official F and 7
notices cover their FX and 7X variants; express-only notices do not imply that
all base-line trains are affected. Profiles retain the train's actual route ID.

Historical support remains visible per endpoint: selected level, independent
event and incident counts, statistics, requested/used context, and fallback
reason. `supported=true` can mean a time-profile fallback during a severe
incident. Only `incident_supported=true` establishes incident-specific
historical support. These counts are not calibrated confidence probabilities.

## Decision policy

Formal `strict_decision` requires fresh usable timing and unambiguous fresh
service evidence for the compared journeys. Severe advice requires a definite
applicable severe incident on the current journey. A Switch needs at least
300 seconds of predicted advantage. A known eligible faster alternative can
support Switch even when other alternatives are unknown; completeness remains
false. Stay requires all supplied alternatives to have been assessed. Unknown
routes cannot be counted as slower, ties, or infeasible by assumption.

If the current journey has no applicable severe incident and every alternative
is assessed, formal output is `STAY / NO_APPLICABLE_SEVERE_INCIDENT`: the severe
trigger did not fire. This does not assert that the current route is fastest;
inspect the separate timing comparison and `best_alternative_savings_seconds`.

Different line names do not prove independent incident exposure. Shared severe
incident IDs appear in `shared_incident_alternatives`; a recommended shared
alternative has `SHARED_SEVERE_INCIDENT_EXPOSURE`. Shared exposure neither adds
a time penalty nor proves service impossible. Such a Switch is a faster
estimated option with shared risk, not an unaffected escape route.

`conditional_timing_decision` compares usable timings without claiming that
archived alert evidence is fresh enough for product advice. It is explicitly
`TIMING_ONLY_NOT_FORMAL_INCIDENT_ADVICE`. Sparse or content-deduplicated alert
archives may therefore show conditional rankings while formal advice abstains.
Unknown and ambiguous service evidence remain visible. The 300-second predicted
threshold is separate from the evaluator's +/-180-second observed practical tie.

## Returned diagnostic schema

Each mode uses `schema_version="severe-comparison-v1"`. Its `routes` retain
every supplied variant, including unavailable ones. Per-route fields include
numeric UTC `eta`, `total_duration_seconds`, `components`, `timing_eligible`,
`comparison_eligible`, context, reasons, rejected candidates, and exact
`selected_legs`. Each selected leg records the service-qualified `trip_id`,
actual line, endpoint stop IDs, baseline/corrected endpoint timestamps,
platform-ready time, traversed stops, and both profile records.

This is an internal algorithm diagnostic schema, not the existing public v1
`Response`. The retained baseline runner and contracts continue to work.
The teammate's API adapter can convert numeric ETAs to ISO strings, map stable
route IDs, and expose the strict decision together with historical support.
Do not present the conditional ranking as a formal severe recommendation.
The profile seal and fit split must accompany evaluation artifacts; production
deployment needs an explicit adapter/version choice rather than silently
changing the retained contract.

## Verified retained-matcher handoff

`MatchedRequestHandoffTests` in `algo/tests/test_severe.py` exercises a complete
synthetic normalized provider request through retained `match_request`, then
transforms its matched evidence into this comparator's input. It uses the
actual request's walking values and current ID, not the October research walks.
The fixture deliberately offers a G departure that is too early for transfer.

| Retained input or matching evidence | Comparator field | Fixture value |
|---|---|---|
| Request `current_itinerary_id` | Decision `current_route_id` | `selected` |
| Supplied itinerary `id` | Supplied route `id` | `selected` |
| Initial WALK `provider_duration_seconds` | `access_walk_seconds` | 60 |
| Intervening WALK `provider_duration_seconds` | `transfer_walk_seconds` | `[45]` |
| Final WALK `provider_duration_seconds` | `egress_walk_seconds` | 20 |
| First matched candidate endpoint pair | First leg endpoints | `P1S` to `P2S` |
| Second matched candidate endpoint pair | Second leg endpoints | `P2S` to `P3S` |
| Matched leg `required_feed_ids` | Each leg `feed_id` | `bdfm`, then `g` |
| Provider subway `route_short_name` | Each leg `route_id` | `F`, then `G` |

For this fixture's known WALK/SUBWAY/WALK/SUBWAY/WALK shape, the transformation
reads walks from request leg indices 0, 2, and 4. Each subway leg requires
exactly one directional endpoint pair across matched candidates and exactly
one required feed. It copies those endpoints into `from_stop_id` and
`to_stop_id`; it does not infer direction from the provider headsign or keep
the matching adapter's chosen train as a fixed forecast.

The new comparator independently selects the first F train and the catchable
G train. Relative to the common cutoff, platform-ready times are +60 and +345
seconds. The G departure at +330 is missed; the selected one leaves at +360
and arrives at +700. Final ETA is +720 seconds: 125 walking, 55 waiting, and
540 riding. The current ID stays `selected` throughout. These are simulated
checks, not measured pilot travel times.

This smoke demonstrates a matched shape, not a general production converter.
An unmatched route, ambiguous endpoint pair, unsupported mode, multiple
unresolved feeds, or absent transfer walking must be returned as an explicit
integration failure. Do not silently omit it from the comparison or replace
its unknown walking duration with zero. A production converter also preserves
supported express aliases and all provider alternatives, including unavailable
ones, so a partial candidate set cannot masquerade as a complete Stay result.

## Local runner

After preparing October snapshots and freezing development profiles:

```sh
.venv/bin/python algo/scripts/run_severe.py \
  --snapshots data/processed/october/2026-10-12.snapshots.jsonl.gz \
  --cutoff 2026-10-12T08:00:00-04:00 \
  --current-route-id g_direct \
  --output data/reports/october-comparison-example.json
```

Supply earlier snapshot files too when relevant incident history precedes the
chosen day. The runner streams train inputs and keeps only the latest as-of
capture per feed; it retains supplied as-of alert versions for incident age.
Use `--mode mta` without a profile file, or `--json` for the full report. This
command never acquires external data and never loads later outcome labels.

Synthetic regression coverage includes endpoint arithmetic, negative corrections,
missed transfers, overtaking, exact train identity, future-data exclusion,
unverified evidence, expired forecasts, service conflicts, meaningful savings,
partial coverage, shared incidents, and express-line aliases:

```sh
PYTHONPATH=.:algo:data .venv/bin/python -m unittest discover \
  -s algo/tests -p test_severe.py
```
