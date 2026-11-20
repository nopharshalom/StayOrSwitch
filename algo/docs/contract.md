# Evaluation API Contract

Version: `1.0`. Status: Step 1 contract for integration review. The API is specified but no live server, MTA integration, or trained model is delivered in this step.

## Purpose and ownership

`POST /v1/evaluate` accepts externally generated itineraries and returns destination-ETA estimates and a Stay/Switch comparison. Google Routes or another provider generates the routes. This service does not generate navigation routes or provide turn-by-turn instructions.

The app/backend preserves the user's selected current itinerary and supplies it alongside candidate alternatives. The algorithm normalizes the agreed inputs, matches MTA data in later implementation stages, estimates complete journey times, and returns structured results for the teammate's UI.

- Machine-readable schema: [evaluate.schema.json](../contracts/evaluate.schema.json), `$defs/Request`, `$defs/Response`, and `$defs/Error`.
- API description: [openapi.json](../contracts/openapi.json).
- Marked simulated examples: [examples](../examples/).
- Evaluation definitions: [November field results](../reports/november-all-forecast-boarding-any-saving.md).

## Request

Send JSON with `Content-Type: application/json`.

The schema requires the declared fields even when their values may be null and rejects undeclared properties. Normalize provider responses into this contract instead of forwarding raw provider JSON. Supply at least one itinerary with at least one leg.

| Field | Meaning |
|---|---|
| `schema_version` | `1.0` for this contract. |
| `request_id` | Client-supplied identifier for matching the response to the request. |
| `data_mode` | `live` for real inputs or `simulated` for marked integration fixtures. |
| `decision_time` | Common reference instant for every candidate's remaining travel time. |
| `user_state` | `NOT_BOARDED`; the first version assumes departure now and no train has been boarded. |
| `origin`, `destination` | Common endpoint locations for all supplied itineraries. |
| `current_itinerary_id` | Identifier of the user's selected current itinerary, or `null` when none has been selected. A non-null value must refer to a supplied itinerary. |
| `itineraries` | Current itinerary and supplied alternatives, each with its own identifier, provider provenance, and ordered legs. |

There is no client-provided minimum-savings threshold, confidence cutoff, detour limit, walking limit, or transfer penalty in version 1.0. Actual walking, waiting, riding, and transfer time still count.

### Itineraries and locations

Each itinerary contains `id`, `provider`, nullable `provider_eta`, and ordered `legs`. Its `provider` contains `name`, nullable `itinerary_id`, and `queried_at`. Provider provenance is necessary because an old estimate must not silently become a current observation. Itinerary `id` values must be unique within the request, and leg `id` values must be unique within their itinerary. `current_itinerary_id` refers to our itinerary `id`, not `provider.itinerary_id`.

The app/backend keeps a stable itinerary identity when refreshing timing for the same selected route structure. A changed sequence of lines or boarding/alighting stops is a different itinerary, not a timing refresh. Later matching may select a different catchable train along the same route. The input legs must join continuously from the common origin to the common destination; include station-transfer walking explicitly. Reused location IDs must describe the same location object.

Every `Location` contains `id`, `name`, and nullable `coordinates`, `provider_place_id`, and `mta_stop_id`. Non-null coordinates contain `latitude` and `longitude`. A provider location identifier is not assumed to be an MTA stop identifier. Null coordinates or stop mappings must not be filled with invented values; they may leave a real itinerary unmatched until a later adapter resolves them.

| Leg field | Meaning |
|---|---|
| `id`, `mode` | Leg identifier and `WALK` or `SUBWAY`; only these modes are supported in this version. |
| `from`, `to` | Start and end locations of the leg. Ordered legs describe one continuous supplied itinerary. |
| `provider_duration_seconds` | Nonnegative provider-estimated duration; required for `WALK`, nullable for `SUBWAY`. Kept distinct from the algorithm's estimate. |
| `provider_departure_at`, `provider_arrival_at` | Nullable provider-estimated times, with their original query timestamp retained. |
| `transit` | Required object for `SUBWAY`, null for `WALK`; not a source of real-time MTA observations by itself. |

For a subway leg, `transit` includes `agency`, `route_short_name`, and nullable `provider_route_id`, `headsign`, `direction_id`, and `provider_trip_id`. Do not infer a unique MTA trip from a line name alone. Provider trip IDs and direction conventions require explicit matching rather than equality assumptions.

## Estimate and data semantics

The response echoes `schema_version`, `request_id`, `data_mode`, `decision_time`, and `current_itinerary_id`; it adds `evaluated_at`, `decision`, `itineraries`, `data_status`, nullable `model_version`, and `warnings`. Evaluation time is distinct from the common decision reference time. Each object in response `itineraries` identifies its supplied itinerary by `id` and has one of three statuses:

| Status | Meaning |
|---|---|
| `ESTIMATED` | A point estimate is available; its comparison eligibility and estimation method still matter. |
| `UNAVAILABLE` | A defensible complete estimate cannot currently be produced. Missing values are not zero minutes. |
| `INFEASIBLE` | Available evidence establishes that the supplied itinerary cannot be taken as evaluated. This differs from an unknown route. |

Route estimates expose `comparison_eligible`, destination `eta`, `total_duration_seconds`, `components` (`walking_seconds`, `waiting_seconds`, `riding_seconds`), `legs`, `reason_codes`, and nullable `uncertainty`. For `UNAVAILABLE` or `INFEASIBLE`, method is `NONE`, eligibility is false, ETA/duration/components/uncertainty are null, and `legs` is empty. The API also identifies the estimation method:

- `MTA_REALTIME`: applicable live MTA transit predictions support the baseline; walking legs can still come from the provider.
- `MODEL_CORRECTED`: at least one subway leg uses an identified model, and other subway legs use either that model or MTA real-time predictions; walking remains a separate provider/schedule input.
- `PROVIDER_FALLBACK`: provider estimates are used as a fallback and labeled accordingly.
- `MIXED`: components use multiple documented estimation sources.
- `NONE`: no estimate is available.

An estimate alone does not establish `comparison_eligible`. A fallback can be shown without supporting a Stay/Switch decision; the fallback fixture intentionally demonstrates ineligible estimates. Never infer eligibility from method or status alone, or change an ineligible result into a recommendation in the UI.

Each response leg contains `leg_id`, `mode`, `start_at`, `end_at`, `duration_seconds`, `wait_before_seconds`, `source`, and nullable `matched_mta_trip_id`. `leg_id` refers to the input leg. Source is `MTA_REALTIME`, `MODEL_CORRECTED`, `PROVIDER`, or `SCHEDULE`. A walking leg has zero preceding wait and no matched MTA trip. A subway leg's preceding wait is included in total waiting, not in its riding duration.

A baseline route must not conceal model-corrected transit legs. Use `MIXED` when transit fallbacks are combined with live/model estimates, and disclose each leg's source. Walking sources are `PROVIDER` or `SCHEDULE`; this version does not train a walking-time model.

`matched_mta_trip_id` is an opaque, service-date-qualified identity assigned by the matching layer, not a bare trip ID copied from a feed. Its resolution must retain agency/feed, service date, route, trip ID, and relevant start time. Raw trip IDs can recur across dates. The simulated identities in examples are not real MTA identifiers.

`data_status` reports `train_feed` and `alerts_feed`, each with `source_updated_at`, `fetched_at`, and status `FRESH`, `STALE`, or `MISSING`. These fields distinguish source age from fetch success. Missing timestamps remain null. An unchanged alert timestamp alone is not evidence that a new service failure occurred. Concrete freshness policy requires later feed validation and must be documented rather than invented by the client.

Each feed entry is a conservative summary across the feeds relevant to the supplied itineraries: any missing required feed yields `MISSING`; otherwise any stale feed yields `STALE`; otherwise `FRESH`. For a non-missing aggregate, source and fetch timestamps are the respective oldest timestamps among those feeds. A missing aggregate has null timestamps even if some individual feeds succeeded. This summary is not a per-route eligibility switch: unaffected routes can remain eligible, while affected routes carry their own reason codes. The later matching layer must retain the underlying per-feed observations internally.

`model_version` is null when no model correction is used. Null uncertainty means uncertainty is not available; do not display a fabricated percentage or convert model absence into a confidence score. A non-null interval specifies `lower_duration_seconds`, `upper_duration_seconds`, `nominal_coverage`, `method`, `calibration_status`, and nullable `calibration_report_id`. `VALIDATED` requires a report identifier; `UNVALIDATED` must not be presented as demonstrated coverage. Interval coverage is not the probability that switching wins. All initial fixtures use null uncertainty, and simulated responses must remain distinguishable from live results.

## Time accounting and reference preservation

- Use timezone-aware timestamps and seconds for durations. Interpret the pilot's service dates in `America/New_York`; never silently interpret a timestamp in a device's local timezone.
- `decision_time` is the agreed snapshot cutoff. Provider query times and feed collection times used for the response must be at or before it, and `evaluated_at` must be at or after it. Source timestamps alone do not prove information was available at that instant. Version 1 timestamps exclude leap-second notation.
- Live implementation must validate client clock skew and snapshot availability. It must not accept arbitrary old/future timestamps as a live snapshot or silently substitute newer observations. Clock-skew tolerance and feed freshness thresholds belong to the later integration policy; this contract does not invent them.
- This cutoff contract assumes a continuously collected/cached MTA snapshot available at decision time. Fetching data only after the request and using it for an earlier cutoff violates the contract. If no appropriate snapshot exists, return unavailable estimates or a service error rather than relabeling newer data.
- All route ETAs are destination arrival estimates, not the next train's arrival at a station. Evaluate every route from the same `decision_time` and user state.
- A complete estimate's duration equals walking plus waiting plus riding. Transfer walking belongs to walking, and transfer waiting belongs to waiting; do not count either twice.
- The destination ETA equals the decision time plus complete estimated duration. Each leg's `end_at` minus `start_at` equals `duration_seconds`; its start follows the previous end (or decision time for the first leg) by `wait_before_seconds`. The final leg ends at destination ETA.
- Preserve the original current-route identity during refresh. Do not replace it with the provider's newly preferred itinerary, or compare a stale current ETA with newly calculated alternatives.
- Walking changes which train can be caught. Time corrections can invalidate a downstream connection; later implementations must recheck those connections.
- Do not add an MTA-trained ETA residual directly to a provider's total ETA. Its existing estimate may already reflect some delay, and historical MTA data does not contain historical Google ETA labels.

## Decision semantics

Response `decision.comparison_scope` is always `SUPPLIED_ITINERARIES`. A result cannot certify that no faster route exists outside that candidate set. `decision.estimated_savings_seconds` compares the selected current itinerary with the recommended itinerary at the same decision time; positive means the recommendation is predicted to save time. It is not observed savings.

| Condition | Decision |
|---|---|
| No current itinerary was selected | `NOT_APPLICABLE`; savings are null. An eligible supplied route may still be identified without a Stay/Switch claim. |
| Current itinerary lacks an eligible estimate or is infeasible | `UNDETERMINED`; savings are null. |
| No alternatives were supplied | `UNDETERMINED`; absence of candidates is not proof that staying is best. |
| An eligible alternative is faster than an eligible current itinerary | `SWITCH`; report the estimated savings. If another alternative remains unassessed, `comparison_complete` is false. |
| Current itinerary is eligible and no eligible alternative is faster, with every supplied alternative assessed as eligible or infeasible | `STAY`; at least one alternative must exist. Savings are zero. An exact tie with the current itinerary favors staying. |
| An alternative remains unknown and no eligible alternative is established to be faster | `UNDETERMINED`; savings are null. |

`recommended_itinerary_id` is nullable and, when present, must refer to an eligible supplied result. It is null for `UNDETERMINED`; `NOT_APPLICABLE` can identify the best eligible supplied result but never reports savings. `comparison_complete` is false for both these actions. For `SWITCH`, it is true only when all alternatives have been assessed as eligible or infeasible; an incomplete Switch means an assessed alternative is faster than the current route, not that every alternative has been ruled out.

Choose the lowest unrounded eligible duration. Exact ties favor the current itinerary; ties between alternatives use their order in the request. There is no hidden minimum savings. This deterministic rule supports UI integration without defining a notification policy.

The first decision reason code is mandatory and follows the decision case: `NO_CURRENT_ITINERARY`, `CURRENT_INFEASIBLE`, `CURRENT_UNAVAILABLE`, `NO_ALTERNATIVES`, `FASTEST_ELIGIBLE_ALTERNATIVE`, `CURRENT_FASTEST_OR_TIED`, or `UNASSESSED_ALTERNATIVES`, in the priority order of the decision table. Remaining reason codes describe additional limitations. They are stable machine-readable values the app can map to user-facing wording; keep official service facts and model inferences distinguishable.

## HTTP and failure behavior

| HTTP status | Meaning |
|---|---|
| `200` | Evaluation response, including partial data, fallbacks, unavailable routes, or an undetermined decision. |
| `400` | Malformed JSON. |
| `422` | Invalid schema, invalid identifier relationships, or unsupported inputs. |
| `503` | The whole evaluation service is unavailable. |
| `500` | Unexpected server error. |

Do not encode a partial feed failure as a successful zero-duration route. Conversely, a valid evaluation with incomplete route data is not automatically a whole-service error. Error responses contain `schema_version`, nullable `request_id`, and `error` with `code`, `message`, and `details` (each containing `path` and `message`). Error codes are `INVALID_REQUEST`, `UNSUPPORTED_VERSION`, `INTERNAL_ERROR`, or `SERVICE_UNAVAILABLE`. Do not show internal diagnostics or credentials to users.

## Using the fixtures and preparing integration

Every fixture is simulated. Each example file wraps `description`, `synthetic`, `http_status`, `request`, and `response`; only its nested `request` is an endpoint request. Pilot address labels are real place names, but fixture stops, lines, paths, and times are illustrative, not verified navigation or MTA results. Fixture coordinates are null deliberately. Use the examples to build UI states and contract checks, not to demonstrate real travel-time performance. Start with [Switch](../examples/01-switch.json), [Stay](../examples/02-stay.json), [no reference](../examples/10-no-reference.json), and [provider fallback](../examples/11-provider-fallback.json).

The deployment URL, authentication mechanism, upstream API-account ownership, and integration contact remain to be agreed. They do not prevent implementation against this versioned contract and simulated examples.
