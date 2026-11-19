# Baseline Journey Estimates

Step 4 is implemented as a Python evaluator and command-line entry point. It
estimates complete supplied journeys from current MTA predictions and provider
walking durations. It does not generate routes, train a model, or start an API
server. The version 1 evaluation response is ready for later service integration.

## Run the pilot

From the repository root, using the environment configured for Step 2:

```sh
.venv/bin/python algo/scripts/run_baseline.py
```

The default addresses are Hayden LIC Apartments, 43-25 Hunter Street, and NYU
Tandon, 6 MetroTech Center. Each invocation requests Google Routes candidates,
collects the required MTA feeds, then establishes one common decision cutoff.
Google data is handled in memory. The command does not automatically save the
response or run a background collector. Public MTA snapshots remain under the
ignored `data/local/mta/` cache.

The initial call has no current itinerary. It can identify the fastest eligible
supplied candidate, but returns `NOT_APPLICABLE / NO_CURRENT_ITINERARY`, not a
Stay/Switch claim. The application must preserve the user's actual selection:

```sh
.venv/bin/python algo/scripts/run_baseline.py --current-itinerary-id SELECTED_ID
```

If that structure is no longer supplied by the provider, the adapter reports the
missing reference instead of silently selecting a different route. The app can
also supply its selected itinerary alongside alternatives using a contract
Request:

```sh
.venv/bin/python algo/scripts/run_baseline.py --request /absolute/path/request.json
```

This mode only reads observations and verified static data already cached at the
request's cutoff; it performs no HTTP requests. An arbitrary old cutoff is not a
request to fetch current feeds and relabel them as historical observations.

Output choices:

- Default: readable minutes, walking/waiting/riding components, destination ETA,
  eligibility, decision, candidate coverage, and provider diagnostic codes.
- `--json`: the version 1 contract Response only.
- `--diagnostics`: the full baseline report, including provenance, selected trip
  IDs, rejected candidates, applicable alerts, original provider ETAs, and limits.
- `--no-provider-fallback`: return unavailable when transit cannot be estimated
  from fresh MTA observations; otherwise coherent provider transit times can be
  displayed but do not support a recommendation.

JSON output can include provider-derived route information. Avoid storing it as
a training dataset or committing it as a fixture. Preserve Google Maps
attribution in the eventual client; the diagnostic report retains the provider
attribution from Step 2. See [live integration](live-integration.md) for key
configuration, source access, and provider data-handling boundaries.

## Calculation and comparison

For each itinerary, begin at the common decision time and process its ordered
legs:

1. Add the supplied access-walking duration to determine platform readiness.
2. Consider fresh, matched trains departing at or after that readiness time.
   Select the earliest predicted arrival at the supplied alighting station,
   which may be a later-departing train that overtakes another service.
3. Add explicit transfer walking, then repeat the catchability calculation for
   the next subway leg. Never add every station's next train wait as measured
   at the initial query time.
4. Add final walking to obtain the destination ETA. Report walking, waiting,
   and riding separately; the three components sum to the complete duration.

For a fixed supplied path with fixed walking durations and unrestricted waiting,
earlier arrival at a transfer can reach every departure a later arrival can
reach. This permits sequential earliest-arrival selection without building a
citywide routing graph. Actual downstream readiness is rechecked after every
choice, including after a provider fallback.

No walking-distance cap, transfer penalty, detour penalty, or minimum savings is
added. Rank unrounded estimated durations. Exact ties favor the selected current
itinerary; ties among alternatives follow their supplied order. A fresh supplied
walking-only itinerary is also eligible and may win. Google TRANSIT queries do
not guarantee that such a candidate will be supplied.

The comparator implements the [contract's decision rules](contract.md): a known
faster eligible alternative can yield `SWITCH` even if another route remains
unknown, with `comparison_complete = false`. `STAY` requires at least one
alternative and assessment of every supplied alternative. An unassessed current
route, absent alternatives, or unresolved alternatives without a known faster
route produce `UNDETERMINED`. Estimated savings are not observed passenger
savings, and recommendations cover only supplied itineraries.

## Evidence and fallback policy

The current thresholds are provisional engineering settings inherited from the
matching report: 180 seconds for train source/fetch age, 300 seconds for service
alert fetch age, and 300 seconds for provider query age. An old alert source
timestamp can remain valid when the feed has been fetched recently. Future,
missing, or contradictory observation timestamps do not become fresh data.

| Evidence | Baseline behavior |
|---|---|
| Every subway leg has applicable fresh MTA observations and service information | `MTA_REALTIME`; comparison eligible |
| Fresh MTA predictions but missing or stale service-alert feed | Show the ETA, flag `ALERTS_UNAVAILABLE`, withhold comparison by default |
| Coherent provider subway departure/arrival available at a catchable time | `PROVIDER_FALLBACK`, or `MIXED` if other subway legs use MTA; display only |
| Fresh supplied walking-only path | `PROVIDER_FALLBACK` because the contract has no separate walking method; comparison eligible without train feeds |
| Stale provider data, missing walk/transfer evidence, no catchable timed option, or ambiguous unsupported inputs | `UNAVAILABLE`; missing time is never zero |
| Missing train, canceled individual train, skipped boarding/alighting stop, or exhausted feed horizon | Reject that candidate; absence alone does not prove route-wide infeasibility |

A structured `NO_SERVICE` alert that matches a candidate and overlaps its actual
departure-to-arrival interval conflicts with its train prediction. The evaluator
excludes that candidate and does not revive the conflicting route using provider
fallback. With no identified train, a relevant overlapping no-service alert also
blocks the unverified fallback. A notice applying only to a different candidate,
or ending before the selected departure, does not invalidate the selected train.

Other alerts are retained as candidate-specific diagnostics. A detour notice does
not replace stop-order evidence: the matched current trip still has to serve the
supplied boarding and alighting stops in order. Alert text is not parsed into
invented route geometry. Station entrance closures and access paths are not
independently verified; provider walking durations are assumed to reach the
boarding platform. A provider reconciliation diagnostic such as
`PROVIDER_PLATFORM_ACCESS_UNVERIFIED` remains visible in the report, along with
the unverified building-entrance limitation.

Aggregate feed states cover only required feeds. A missing feed for one route
does not automatically disable unaffected routes. Provider transit fallbacks
remain ineligible even when their durations look plausible. Pure walking has no
transit prediction to verify, so its documented eligibility differs.

## Python integration and validation

```python
from stayorswitch.baseline import evaluate_integration

# integration is an in-memory result from integrate_live or integrate_supplied.
report = evaluate_integration(integration)
response = report["response"]
```

`evaluate_baseline(request, matching)` is the lower-level entry point. Matching
reports are internal artifacts bound to the complete normalized request by a
canonical SHA-256 fingerprint; retaining IDs while changing a line, location, or
walking duration requires rematching. Both entry points validate the Request and
the resulting Response against the existing schema and cross-field invariants.
Detailed diagnostic codes stay outside the fixed contract reason-code enum.

The output has `model_version = null` and `uncertainty = null`. There is no
trained correction or calibrated confidence interval. Original provider ETA is
preserved separately in route diagnostics; an MTA residual is never added to a
provider's total ETA. Model training and integration remain Steps 5 and 6.

Run the synthetic checks with:

```sh
PYTHONPATH=algo .venv/bin/python -m unittest discover -s algo/tests
.venv/bin/python algo/scripts/validate_contract.py --self-test
```

Checks cover component arithmetic, transfers, missed departures, overtaking,
subsecond ranking, partial coverage, reference preservation, walking-only
alternatives, stale/future observations, provider and mixed fallbacks, selected
candidate alert relevance, canceled/skipped trains, request binding, and
controlled invalid-input behavior. They establish implementation behavior, not
real-world prediction accuracy.

## Observed live smoke check

At `2026-11-19T21:11:57.183426Z`, the pilot returned two supported unique
itineraries with complete `MTA_REALTIME` estimates and fresh relevant feeds:

| Route | Walking | Waiting | Riding | Total |
|---|---:|---:|---:|---:|
| First accepted itinerary | 15.20 min | 0.08 min | 20.75 min | 36.03 min |
| Second accepted itinerary | 8.90 min | 6.81 min | 28.75 min | 44.46 min |

No current itinerary was supplied, so the result correctly identified the first
eligible candidate with `NOT_APPLICABLE / NO_CURRENT_ITINERARY`. These are a
single live integration check using predictions and provider walking assumptions,
not measured arrival accuracy, realized savings, or a claim that all possible
alternatives were covered. Current results change as service and provider
candidates change.
