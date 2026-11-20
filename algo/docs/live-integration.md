# Step 2: Provider and MTA Live Integration

Status: implemented for the pilot, with real upstream smoke checks on 2026-11-19.
This package links supplied route legs to station identities and candidate MTA
services. It does not implement destination ETA estimation, model training,
Stay/Switch comparison, or the `/v1/evaluate` server. Those remain later steps.

## Local setup

From the repository root, use Python 3.9 or later:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r algo/requirements-live-lock.txt
cp -n .env.example .env
chmod 600 .env
```

Fill in `GOOGLE_ROUTES_API_KEY` locally in `.env`. The existing configured `.env`
must not be overwritten. Environment variables override file values. Local
settings are parsed as plain data, not executed as shell commands. The credential
is sent only in an HTTPS request header to the Google Routes endpoint; request
headers and credential values are not logged. `.env`, virtual environments, and
`data/local/` are ignored by Git. `.env.example` contains no credential.

`GOOGLE_ROUTES_IPV4=true` is the default. Initial Python and default-curl requests
returned HTTP 403 `ACCESS_DENIED`; a curl IPv4 request succeeded with HTTP 200,
and the HTTPX client with an IPv4 local address also succeeded. Keep the network
address family consistent with the key's IP restrictions. A changed network or
deployment needs its own verified egress allowlist. TLS verification is enabled;
the client does not follow redirects or automatically retry billable requests.

## Run the pilot

```bash
.venv/bin/python algo/scripts/run_live_integration.py
```

The defaults are Hayden LIC Apartments at 43-25 Hunter Street and NYU Tandon at
6 MetroTech Center. Override addresses using `--origin` and `--destination`.
Use `--json` to send the full in-memory integration report to a consuming program.
The default console summary includes candidate counts, feed freshness, accepted
route IDs, matching states, and provider issues. A successful process exit means
valid input integration completed; inspect per-route matching states for missing
or unsupported evidence. It is not a statement that a journey is feasible or best.

No current route is selected by default. To refresh a chosen route structure,
pass its stable ID with `--current-itinerary-id`. If that route is absent or
unsupported in the refreshed provider response, integration reports
`CURRENT_ITINERARY_MISSING`; it never substitutes Google's first route.
The app can instead supply the current itinerary together with alternatives.

Google raw responses are processed in memory by this command, without automatic
archival or inclusion in test fixtures. Provider-derived data remains subject to
[Google's data-handling and attribution requirements](https://developers.google.com/maps/documentation/routes/policies).
The app teammate should retain Google attribution and determine the permitted
display/storage behavior before release. MTA data and local acquisition metadata
are cached under `data/local/mta/`; no historical pilot week is downloaded here.

## Fixed-cutoff integration and collection

Collect MTA observations explicitly, without a background service:

```bash
.venv/bin/python algo/scripts/collect_mta.py --routes A,C,E,F,G --samples 1
```

For repeated collection, set `--samples` and `--interval-seconds` (minimum 15,
default 30). This is a finite foreground collector. It stores whole-feed
snapshots, including failed-fetch observations. A later failed fetch never
silently revives an earlier successful set of trains. Equal-time conflicting
observations are handled conservatively. Files are local cache observations,
not verified arrival outcomes or model labels.

A backend that already has a valid version 1.0 Request can run:

```bash
.venv/bin/python algo/scripts/run_live_integration.py --request /absolute/path/request.json --json
```

This mode performs no new provider or MTA HTTP requests. It only reads snapshots
collected at or before the supplied `decision_time`, plus verified static data
available at that cutoff. Missing evidence remains missing. For app integration,
run a collector independently so observations exist before each fixed cutoff.
The live pilot command instead collects inputs first and establishes a new
common cutoff after collection; it never relabels later data as an earlier view.

## Provider normalization

- Group explicit consecutive walking steps and preserve their durations.
- Support MTA subway and walking. A subway preference in a Google request does
  not guarantee that every returned transit step is subway; actual modes and
  agencies are checked.
- Build itinerary IDs from stable endpoints, lines, stops and mode sequence,
  excluding train times, provider ordering, headsign changes and caller endpoint
  display-name changes. Provider stop-name/coordinate changes conservatively
  produce a different structure until a durable stop identity is available.
- Deduplicate repeated departures on the same route structure and retain the
  earliest complete provider arrival. Preserve all source indices in provenance.
- Keep Google's reported duration and train timestamps separately. Derive the
  provider destination arrival from the last transit arrival plus explicit
  egress walking, and expose any difference from query time plus route duration.
  This is normalization of provider information, not an MTA-corrected ETA.
- Reject missing walking durations, disconnected legs, impossible transfer
  clocks, and consecutive transit legs without an explicit transfer walk.
  Waiting gaps are never converted into invented transfer-walking durations.
- Preserve `null` for unknown MTA trip IDs, directions and endpoint coordinates.

Provider walking geometry must join within 25 metres. An explicit walking step
can meet a named station representative point within a configurable 250 metres;
an offset over 25 metres is disclosed as `PROVIDER_PLATFORM_ACCESS_UNVERIFIED`.
The original walking duration is unchanged. These are technical mapping
tolerances, not limits on how far the user may walk. Building entrances and
station-internal access have not been independently measured.

## MTA observations and matching

[Source URLs](../../data/mta-sources.json) use official MTA train feeds, subway
alerts, and regular static GTFS. Static data provides station identities and
advisory line membership, not a route-planning graph or authoritative detour
schedule. Actual fresh trip stopping patterns can add evidence of reroutes.

The parser preserves service dates, stop-event presence, cancellation/skipped/
no-data relationships, NYCT direction and tracks, replacement periods, vehicle
observations and structured alert selectors. Missing values are not converted
to zero. Differential feeds are explicitly unsupported rather than treated as
complete snapshots. Trip identities include agency, feed, service date, route,
raw trip ID and start time, preventing collisions across service dates.

Station matching considers name, location and line membership. Nearby ambiguous
stations remain unresolved. Candidate trains must serve boarding and alighting
platforms in the correct order, have usable predictions, and depart after the
provider walking steps make the platform reachable. For transfers, the previous
linked arrival plus explicit transfer walking determines downstream readiness.
If an earlier leg is unresolved, downstream reachability remains unknown.
An arrival-time proxy for a missing boarding departure is explicitly labeled.

Service alerts are linked using their structured selectors and active periods,
including known notices overlapping a candidate's upcoming journey. Relevant
intermediate stops are considered. Text alone does not establish that an entire
route is infeasible. Missing alert data is different from a successful empty feed.

`MATCHED`, `PARTIAL`, and `UNMATCHED` describe the quality of candidate-service
linkage. `MATCHED` does not identify Google's exact train, confirm physical
platform access, or guarantee a complete journey. The report intentionally
contains no corrected destination ETA or Stay/Switch action.

## Provisional policies

| Setting | Default | Meaning |
|---|---:|---|
| Train source/fetch age | 180 seconds | Reject stale live train evidence. |
| Alert fetch age | 300 seconds | An unchanged source timestamp alone does not expire alerts. |
| Provider query age | 300 seconds | Old route timing is not silently refreshed by matching. |
| Static cache age | 24 hours | Refresh matching metadata for new live runs. |
| Station mapping radius | 200 metres | Technical matching tolerance, not a walking limit. |

These values are engineering settings, not empirically calibrated confidence or
product preference. No arbitrary walking, transfer, detour or minimum-savings
penalty is introduced. Source/collection times after the snapshot cutoff are
unavailable; future predicted arrivals are expected and are not future evidence.

For the current recommendation API and evaluation, see the [algorithm guide](../README.md).
