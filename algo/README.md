# Delay-Aware ETA and Stay/Switch Roadmap

Status: Steps 1 through 5 are implemented for the pilot, including offline component-model training and frozen final-test evaluation. The riding-segment model passed the predeclared component gate; arrival and departure models did not outperform the simple historical correction on the primary RMSE metric. The live comparator remains the Step 4 baseline. Labels are inferred prediction proxies, not physical arrival observations. No evaluation API server is delivered yet.

## Step 5: Component model experiments

The [training and evaluation guide](docs/model-training.md) describes separate
arrival, departure, and riding-duration residual models, their two reference
methods, chronological holdouts, and operating-support fallbacks. The
[pre-test protocol](docs/model-protocol.md) and
[training configuration](config/model-training.json) define the experiment.
See the [measured results and model card](reports/model-results.md),
[final-test metrics](reports/model-test.json), and
[pre-test frozen manifest](reports/model-frozen.json).

From the repository root:

```sh
.venv/bin/python -m pip install -r algo/requirements-model.txt
.venv/bin/python data/scripts/build_model_data.py
.venv/bin/python algo/scripts/train_models.py
.venv/bin/python algo/scripts/evaluate_models.py
```

Model data and shared feature construction stay under `data/`; training,
inference, and evaluation stay under `algo/`. The pilot uses a documented,
event-balanced sample of the two-week dataset. Final-test performance is opened
only after configuration and model artifacts are frozen. An existing frozen
experiment cannot be overwritten by the training command.

These offline component experiments do not activate learned corrections in the
live baseline. They do not establish passenger destination accuracy or realized
time savings. Integration and the served evaluation API remain Step 6.

## Steps 3 and 4: Parallel development

The historical-data pipeline and live journey comparator are independent tracks.
Data source files and processing code live under `data/`; the comparator lives
under `algo/`. Both preserve decision-time provenance and explicit unavailable
states. Neither trains a model or starts an API server.

- [Historical processing, source manifests, and quality reports](../data/README.md)
- [Baseline comparison commands and limitations](docs/baseline.md)

From the repository root, after installing `algo/requirements-live.txt`:

```bash
# Step 3: reproduce the configured historical dataset.
.venv/bin/python data/scripts/build_history.py

# Step 4: compare current provider candidates using live MTA estimates.
.venv/bin/python algo/scripts/run_baseline.py
```

The baseline returns the existing version 1 Response with destination ETA,
walking/waiting/riding components, per-leg sources, and comparison eligibility.
Pass the user's selected `--current-itinerary-id` to establish the Stay reference.
Without one, the baseline can identify the fastest eligible supplied candidate
but returns `NOT_APPLICABLE` for Stay/Switch. It does not silently select a current
route. Provider-only transit fallbacks remain display-only; a fresh supplied
walking-only itinerary can compete using its stated walking duration.

## Step 2 live integration

See [setup, commands, data policies, and current limitations](docs/live-integration.md).
The pilot command reads the local API credential, retrieves provider candidates,
and links supported route legs to as-of MTA observations:

```bash
.venv/bin/python algo/scripts/run_live_integration.py
```

`MATCHED` means live candidate services were linked, not that an ETA or Stay/Switch
recommendation has been computed. All generated routes remain the provider's work.

## Step 1 integration package

- [API contract and decision semantics](docs/contract.md)
- [OpenAPI 3.1 description](contracts/openapi.json)
- [JSON Schema: Request, Response, and Error](contracts/evaluate.schema.json)
- [Simulated request/response examples](examples/README.md)
- [Evaluation criteria](docs/evaluation.md)

The teammate can build against static simulated responses while live integration and training are developed separately. The contract is ready for review; upstream provider ownership and deployment details are still to be coordinated.

Validate the package locally with Python 3.9 or later, from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r algo/requirements-contract.txt
.venv/bin/python algo/scripts/validate_contract.py --self-test
```

This offline check validates the JSON Schema, local OpenAPI references, fixture schemas, cross-field timing/identity/decision invariants, and deliberately invalid boundary cases. It does not start a server, predict travel times, or establish model performance. It is not a full OpenAPI conformance validator.

## Goal and boundaries

StayOrSwitch is a decision companion, not a navigation app. Google Routes or another external provider supplies the user's current itinerary and candidate alternatives. Our algorithm re-estimates their destination arrival times using historical delay patterns and current MTA conditions, especially during disruptions, and determines whether a supplied alternative is expected to be faster.

The teammate owns final UI design and app development. Our deliverable is a reusable algorithm, an evaluation API, and English integration documentation. An OTP routing engine, a street graph, address-search UI, and turn-by-turn navigation are outside this version's scope.

## Confirmed pilot

- Origin: Hayden LIC Apartments by Rockrose, 43-25 Hunter Street, Long Island City, NY 11101.
- Destination: NYU Tandon School of Engineering, 6 MetroTech Center, Brooklyn, NY 11201.
- Verify building entrance coordinates before door-to-door evaluation. Keep this test case configurable.
- User state: not yet on a train, departing now. Modes: subway and walking.
- Historical source: Subway Data NYC archives for 2026-11-02 through 2026-11-15 inclusive, expanded to two weeks on 2026-11-19. Distinguish archive calendar dates from America/New_York trip service dates and report weekdays, Saturdays, and Sundays separately.
- Objective: lowest estimated total door-to-door time among feasible supplied candidates.
- Do not impose arbitrary walking, transfer, or detour caps or penalties. Include actual walking and transfer durations.
- Evaluate supplied alternatives using nearby different stations or detours, including routes through other areas.
- Candidate coverage depends on the external provider; do not claim the fastest possible route across the entire network.

## Processing flow

Provider current itinerary and alternatives -> normalized legs -> matching MTA observations -> delay-aware destination ETA estimates -> comparison against the current itinerary -> Stay/Switch result for the app.

Train-arrival predictions are intermediate inputs. The main output is estimated arrival at the final destination, with its data basis and uncertainty, not a guaranteed actual arrival time.

## Step 1: Define the algorithm contract and evaluation criteria

- Accept the current itinerary and alternatives from the application backend or a thin provider adapter. The external provider performs route planning.
- Normalize walking/transit legs, line identifiers, directions, boarding/alighting stops, timings, itinerary identifiers, and provider query timestamps.
- Preserve the user's selected current itinerary as the Stay reference. Refresh its timing without silently replacing it with the provider's newly preferred route.
- Define a versioned `/v1/evaluate` contract. Without a current itinerary, return estimates without inventing a Stay reference.
- Return per-route destination ETA, total/component durations, recommended itinerary identifier, estimated savings, decision reason codes, data timestamps, model version, and fallback/unavailable status.
- Define responses for missing alternatives, stale data, unmatched trips, and infeasible routes. Missing values must not be interpreted as zero travel time.
- Agree on evaluation criteria for ETA error, route comparisons, and disruption conditions before training.

**Deliverable:** a provider-independent contract and clearly marked simulated fixtures for the teammate's integration work.

## Step 2: Connect provider itineraries and real-time MTA data

- Obtain real route-provider responses and convert them into the contract's common format.
- Connect current train feeds and official service information.
- Map provider stations, lines, directions, and timings to MTA stops and candidate trips, using static GTFS and station metadata where needed. Do not assume provider trip IDs match MTA IDs.
- Verify which departures can be reached after walking to the boarding platform.
- Track missing/stale data, ambiguous matches, cancellations, skipped stops, and known service changes.
- Preserve original provider ETA and MTA predictions separately for later comparison.

**Deliverable:** normalized itinerary legs linked to live MTA observations, with unmatched or unsupported portions explicitly identified.

## Step 3: Prepare historical features and labels

- Retrieve the fourteen selected daily raw GTFS-Realtime archives and accompanying CSVs; verify coverage and contents. Validate one weekday and one weekend sample before processing the full window. Keep source files and all historical processing code under `data/`.
- Extract decision-time ETA, recent ETA changes, route, stop, direction, vehicle state, headways, day type, time of day, and the stopping pattern known at that time. Extract contemporaneous alerts only when archived evidence exists; otherwise mark alert availability unknown.
- Construct subsequent arrival and, where supported, segment-travel labels. Record quality and derivation and validate a sample independently.
- Treat CSV and vehicle-derived arrival times as inferred labels, not verified physical arrival times.
- Check gaps, duplicates, trip continuity, cross-day records, and changed stopping patterns. Cover alternatives' lines as well as the current route.
- Reserve whole dates for validation/testing, keep each trip in one split, and report weekdays, Saturdays, and Sundays separately. Exclude future updates and notices from input features. A longer planned weekend headway is not itself an unexpected delay.

**Deliverable:** reproducible features, quality-marked labels, and chronological evaluation splits. Two weeks and two weekends support a pilot, not long-term or general weekend-performance claims.

## Step 4: Build journey estimates and comparisons without a learned model

- Use applicable MTA real-time predictions and explicitly documented provider or schedule fallbacks.
- Calculate journeys sequentially: access walking, waiting for a catchable train, riding, transfer walking and waiting, and final walking.
- Select departures based on when the user can reach each platform; do not simply add each station's next-train waiting time at the initial query time.
- Re-estimate the current itinerary and all alternatives at the same decision time and from the same user state.
- Return baseline destination ETAs and the fastest feasible supplied candidate, with no extra walking, transfer, or detour penalties.
- Keep component estimates and data sources available for inspection so later model corrections can be evaluated against this baseline.

**Deliverable:** a runnable baseline journey comparator and an interpretable result for the pilot query. The learned model is not required for this milestone.

## Step 5: Train and validate delay-aware time estimates

- Start by predicting residual error in current MTA train-arrival estimates, especially during repeated revisions and disruptions.
- Compare with unmodified MTA estimates and simple historical corrections on held-out dates, in normal and disrupted conditions.
- Estimate remaining riding and transfer components too; a first-train waiting-time model alone is not a destination-ETA model.
- Document uncertainty, supported lines/horizons, and fallback behavior.
- Do not add an MTA-trained residual blindly to a provider's total ETA. MTA history does not contain historical Google ETA predictions; a Google-specific residual model requires its own paired observations.

**Deliverable:** evaluated time-estimation components with documented limitations.

## Step 6: Integrate the model and expose Stay/Switch evaluation

- Integrate the evaluated model from Step 5 into the baseline comparator from Step 4 and expose it through `/v1/evaluate`.
- Evaluate all routes at the same decision time from the same user state.
- Reconstruct access walking, waiting for a catchable train, riding, transfer walking/waiting, and final walking sequentially.
- Apply corrections to the components they predict and avoid counting a delay already reflected in an estimate twice.
- Recheck trains and downstream connections after time corrections. Request refreshed provider alternatives when needed rather than silently inventing routes.
- Check shared disrupted segments: different line names do not establish independent alternatives.
- Return Stay/Switch only when routes can be meaningfully compared; otherwise return an unavailable or insufficient-data state. No supplied alternative is not proof that none exists.
- Report estimated savings and uncertainty separately. Do not invent a minimum-savings threshold or risk preference without a product decision.

**Deliverable:** an evaluation API explaining revised destination ETA and whether an available alternative is expected to be faster.

## Step 7: Validate the integrated system and hand it off

- Use Hayden LIC to NYU Tandon at 6 MetroTech Center as the primary configurable test case.
- Check normal operation, delays, reroutes, missing data, and missed-transfer scenarios.
- Compare baseline and model estimates on identical candidate sets and decision times.
- Evaluate component error, destination-ETA error where suitable labels exist, missed connections, and route-selection outcomes, especially during delays.
- Separate inferred replay outcomes from independently observed passenger arrivals. Full historical journey replay requires date-appropriate service arrangements and defensible candidate availability; today's provider output is not historical evidence.
- Deliver algorithm source, model artifacts or retrieval instructions, training/evaluation scripts, data manifests, and reproducible service startup.
- Provide English API documentation, pilot examples, error/fallback examples, and a client integration example. The teammate handles app UI, maps, and interactions.

**Deliverable:** an evaluated, runnable algorithm service with integration materials.

## Parallel work

Agree on the Step 1 contract first, then run the following tracks in parallel:

| Track | Sequence | Dependency |
|---|---|---|
| Real-time integration and comparison | Step 2 -> Step 4 | Shared contract and provider/MTA access |
| Historical data and modeling | Step 3 -> Step 5 | Feature definitions, label quality, and chronological splits |
| Teammate's app development | Start after Step 1 | Clearly marked simulated requests/responses |
| Algorithm integration and handoff | Step 6 -> Step 7 | Working baseline comparator and evaluated model |

Define evaluation cases early. The first development milestone is an interpretable baseline comparison of a supplied current itinerary and alternatives using live MTA information; model training can continue independently.

## Items to settle before live-data integration

- Route-provider access: which backend calls the provider, account/API configuration, and how responses reach the algorithm. Keep credentials outside committed files.
- Interface ownership: identify the teammate responsible for coordinating request/response integration.
- First delivery date: use it to schedule the pilot scope and validation depth.

Google Routes is the pilot provider; its development credential is configured
locally and never committed. The baseline evaluator uses the existing contract;
the original API response fixtures remain explicitly simulated. Step 5's offline
model experiment is complete. Model/service integration and integrated
validation/handoff remain Steps 6-7. Final backend ownership and delivery timing
still need coordination.

## Repository organization

- `algo/`: provider adapters, ETA estimation, training, comparison logic, evaluation, and documentation.
- `data/`: data source files, downloaders, historical processing code, data tests, manifests, quality reports, and ignored large raw/processed artifacts.
- Repository-wide conventions: [AGENTS.md](../AGENTS.md).

## References

- [MTA developer resources](https://www.mta.info/developers)
- [Google Routes transit requests](https://developers.google.com/maps/documentation/routes/transit-route)
- [Google Routes alternatives](https://developers.google.com/maps/documentation/routes/alternative-routes)
- [Subway Data NYC downloads](https://subwaydata.nyc/browse-the-data)
- [Subway Data NYC arrival inference](https://subwaydata.nyc/how-it-works)
