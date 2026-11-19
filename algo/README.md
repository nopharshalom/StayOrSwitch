# Delay-Aware ETA and Stay/Switch Roadmap

Status: planned. Scope revised on 2026-11-19. No prediction model or decision API is implemented yet.

## Goal and boundaries

StayOrSwitch is a decision companion, not a navigation app. Google Routes or another external provider supplies the user's current itinerary and candidate alternatives. Our algorithm re-estimates their destination arrival times using historical delay patterns and current MTA conditions, especially during disruptions, and determines whether a supplied alternative is expected to be faster.

The teammate owns final UI design and app development. Our deliverable is a reusable algorithm, an evaluation API, and English integration documentation. An OTP routing engine, a street graph, address-search UI, and turn-by-turn navigation are outside this version's scope.

## Confirmed pilot

- Origin: Hayden LIC Apartments by Rockrose, 43-25 Hunter Street, Long Island City, NY 11101.
- Destination: NYU Tandon School of Engineering, 6 MetroTech Center, Brooklyn, NY 11201.
- Verify building entrance coordinates before door-to-door evaluation. Keep this test case configurable.
- User state: not yet on a train, departing now. Modes: subway and walking.
- Historical source: Subway Data NYC archives for 2026-11-09 through 2026-11-15 inclusive, using America/New_York service dates.
- Objective: lowest estimated total door-to-door time among feasible supplied candidates.
- Do not impose arbitrary walking, transfer, or detour caps or penalties. Include actual walking and transfer durations.
- Evaluate supplied alternatives using nearby different stations or detours, including routes through other areas.
- Candidate coverage depends on the external provider; do not claim the fastest possible route across the entire network.

## Processing flow

Provider current itinerary and alternatives -> normalized legs -> matching MTA observations -> delay-aware destination ETA estimates -> comparison against the current itinerary -> Stay/Switch result for the app.

Train-arrival predictions are intermediate inputs. The main output is estimated arrival at the final destination, with its data basis and uncertainty, not a guaranteed actual arrival time.

## Step 1: Define the itinerary input and evaluation contract

- Accept the current itinerary and alternatives from the application backend or a thin provider adapter. The external provider performs route planning.
- Normalize walking/transit legs, line identifiers, directions, boarding/alighting stops, timings, itinerary identifiers, and provider query timestamps.
- Preserve the user's selected current itinerary as the Stay reference. Refresh its timing without silently replacing it with the provider's newly preferred route.
- Define a versioned `/v1/evaluate` contract. Without a current itinerary, return estimates without inventing a Stay reference.
- Return per-route destination ETA, total/component durations, recommended itinerary identifier, estimated savings, decision reason codes, data timestamps, model version, and fallback/unavailable status.

**Deliverable:** a provider-independent contract and clearly marked simulated fixtures for the teammate's integration work.

## Step 2: Connect MTA data and establish baseline estimates

- Connect current train feeds and official service information.
- Map provider stations, lines, directions, and timings to MTA stops and candidate trips, using static GTFS and station metadata where needed. Do not assume provider trip IDs match MTA IDs.
- Track missing/stale data, ambiguous matches, cancellations, skipped stops, and known service changes.
- Build a baseline evaluator using applicable real-time estimates and documented provider or schedule fallbacks.
- Keep provider ETA and MTA-based estimates separate for comparison.

**Deliverable:** provider itineraries matched to MTA observations where possible, with a working baseline ETA evaluator.

## Step 3: Prepare historical features and labels

- Retrieve the seven selected daily raw GTFS-Realtime archives and accompanying CSVs; verify coverage and contents.
- Extract decision-time ETA, recent ETA changes, route, stop, direction, vehicle state, headways, time of day, and alerts already available at that time.
- Construct subsequent arrival and, where supported, segment-travel labels. Record quality and derivation and validate a sample independently.
- Treat CSV and vehicle-derived arrival times as inferred labels, not verified physical arrival times.
- Check gaps, duplicates, trip continuity, cross-day records, and changed stopping patterns. Cover alternatives' lines as well as the current route.
- Reserve whole dates for validation/testing, keep each trip in one split, and report weekdays and weekends separately. Exclude future updates and notices from input features.

**Deliverable:** reproducible features, quality-marked labels, and chronological evaluation splits. A single week does not establish long-term generalization.

## Step 4: Train delay-aware time estimates

- Start by predicting residual error in current MTA train-arrival estimates, especially during repeated revisions and disruptions.
- Compare with unmodified MTA estimates and simple historical corrections on held-out dates, in normal and disrupted conditions.
- Estimate remaining riding and transfer components too; a first-train waiting-time model alone is not a destination-ETA model.
- Document uncertainty, supported lines/horizons, and fallback behavior.
- Do not add an MTA-trained residual blindly to a provider's total ETA. MTA history does not contain historical Google ETA predictions; a Google-specific residual model requires its own paired observations.

**Deliverable:** evaluated time-estimation components with documented limitations.

## Step 5: Compare current and alternative itineraries

- Evaluate all routes at the same decision time from the same user state.
- Reconstruct access walking, waiting for a catchable train, riding, transfer walking/waiting, and final walking sequentially.
- Apply corrections to the components they predict and avoid counting a delay already reflected in an estimate twice.
- Recheck trains and downstream connections after time corrections. Request refreshed provider alternatives when needed rather than silently inventing routes.
- Check shared disrupted segments: different line names do not establish independent alternatives.
- Return Stay/Switch only when routes can be meaningfully compared; otherwise return an unavailable or insufficient-data state. No supplied alternative is not proof that none exists.
- Report estimated savings and uncertainty separately. Do not invent a minimum-savings threshold or risk preference without a product decision.

**Deliverable:** an evaluation API explaining revised destination ETA and whether an available alternative is expected to be faster.

## Step 6: Evaluate and hand off the algorithm

- Compare baseline and model estimates on identical candidate sets and decision times.
- Evaluate component error, destination-ETA error where suitable labels exist, missed connections, and route-selection outcomes, especially during delays.
- Separate inferred replay outcomes from independently observed passenger arrivals. Full historical journey replay requires date-appropriate service arrangements and defensible candidate availability; today's provider output is not historical evidence.
- Deliver algorithm source, model artifacts or retrieval instructions, training/evaluation scripts, data manifests, and reproducible service startup.
- Provide English API documentation, pilot examples, error/fallback examples, and a client integration example. The teammate handles app UI, maps, and interactions.

**Deliverable:** an evaluated, runnable algorithm service with integration materials.

## Parallel work

Agree on the contract first. Provider normalization and live MTA matching (Steps 1-2) can proceed alongside historical preparation and modeling (Steps 3-4). The teammate can use simulated responses immediately. Build comparison against baseline estimates before the learned model is ready, integrate in Step 5, then complete validation and handoff in Step 6.

## Repository organization

- `algo/`: provider adapters, ETA estimation, training, comparison logic, evaluation, and documentation.
- `data/`: dataset documentation, manifests, and organization.
- Repository-wide conventions: [AGENTS.md](../AGENTS.md).

## References

- [MTA developer resources](https://www.mta.info/developers)
- [Google Routes transit requests](https://developers.google.com/maps/documentation/routes/transit-route)
- [Google Routes alternatives](https://developers.google.com/maps/documentation/routes/alternative-routes)
- [Subway Data NYC downloads](https://subwaydata.nyc/browse-the-data)
- [Subway Data NYC arrival inference](https://subwaydata.nyc/how-it-works)
