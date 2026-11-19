# Routing and Prediction Roadmap

Status: planned. This document describes the implementation sequence; it does not claim that routing, model training, or evaluation is already implemented.

## Goal

Users enter an origin, destination, and departure time. StayOrSwitch automatically generates feasible subway-and-walking routes, including different nearby boarding and alighting stations, and ranks them using historical delay patterns learned by a model together with current MTA conditions.

Candidate generation is automatic: manually authored route lists are not a prerequisite. The first version focuses on subway travel, walking, nearby station alternatives, and limited transfers. More complex detours can follow.

Recommendations should identify the best estimated option among the generated candidates under the user's constraints, rather than promise a globally optimal or guaranteed fastest journey.

## User flow

Origin and destination -> departure time and walking/transfer preferences -> automatic candidate routes -> real-time estimates corrected by the historical model -> recommended routes with walking, transfers, and uncertainty.

## Step 1: Set up the routing engine

- Deploy OpenTripPlanner (OTP) and select a supported version.
- Import MTA static GTFS and OpenStreetMap data for the service area.
- Connect address lookup so user-entered addresses become coordinates.
- Verify station entrances, directions, walking connections, and transfer links.
- Keep track of input data versions and service dates.

**Deliverable:** a routing service that accepts origin/destination coordinates and departure time and returns subway-and-walking itineraries.

## Step 2: Generate candidate routes automatically

- Search from the origin coordinates to the destination coordinates, allowing walking access to nearby stations at both ends.
- Apply user limits on walking and transfers.
- Run additional searches within those limits to explore different stations and line combinations; adjust walking and transfer preferences as needed.
- Add automatic searches through selected transfer locations when useful for detours. Depending on feasibility, these can include riding farther before transferring, traveling in the opposite direction first, or walking between stations.
- Merge results, remove duplicates and pointless loops, and check service availability, direction, and time-feasible connections.
- Preserve a diverse set of candidates for scoring. Default routing filters may discard alternatives that become attractive after model corrections.

**Deliverable:** multiple automatically generated, feasible routes with their walking, transit, and transfer legs. No manually maintained route library is required.

## Step 3: Prepare historical training and evaluation data

- Use archived GTFS-Realtime snapshots, such as Subway Data NYC, as the historical source.
- Extract route, station, direction, time of day, day of week, current ETA, recent ETA revisions, vehicle state, headways, and alerts available at the decision time.
- Construct subsequent arrival labels and document their derivation and confidence. Archive CSV arrival times are inferred values, not independently verified physical arrival times.
- Check coverage, gaps, duplicates, cross-day records, and changes in stopping patterns; validate a sample of arrival labels.
- Split training, validation, and test data chronologically, keeping observations of the same trip together.
- Exclude future ETA revisions and future alerts from model inputs. Historical replay also requires service arrangements appropriate to the date being evaluated.

**Deliverable:** documented training and evaluation datasets with reproducible features, labels, and time-based splits.

## Step 4: Train and validate a delay prediction model

- Start by predicting the residual error in the current MTA ETA: how much later or earlier the train is likely to arrive than that ETA.
- Compare against the baseline of using the unmodified MTA ETA, as well as a simple historical correction.
- Evaluate accuracy across routes, stations, prediction horizons, and disruption conditions.
- Estimate uncertainty where supported by the data.
- Use real-time estimates or historical statistics for other journey components initially. A first-train ETA model alone does not predict the entire journey.

**Deliverable:** an evaluated ETA correction model, with documented strengths and limitations. Any claimed improvement must be supported by held-out results.

## Step 5: Score routes with real-time conditions

- Connect current MTA train feeds and service information, and verify their mapping to the routing network.
- Combine decision-time features with the trained model to correct relevant arrival/departure estimates.
- Calculate each journey sequentially: access walking, waiting, riding, transfer walking and waiting, and final walking.
- Select trains the user can actually catch after walking or transferring; recalculate connections after time corrections.
- Avoid adding historical delay twice when it is already reflected in the real-time ETA.
- Check shared disrupted segments: a different line may still use the affected infrastructure.
- Rank candidates by estimated arrival time under user constraints, and present walking, transfers, uncertainty, and any relevant additional fare separately.

**Deliverable:** a ranked set of feasible routes with estimated total remaining travel time and an explanation of the recommendation.

## Step 6: Evaluate the system and complete the interface

- Replay historical decision times using only information available at each time; use later observations only for evaluation.
- Compare identical candidate sets with and without model corrections to isolate the model's contribution.
- Evaluate candidate coverage separately so missing alternatives are not confused with prediction errors.
- Assess ETA error, estimated arrival outcomes, missed transfers, unnecessary detours, and walking/transfer burden. Distinguish replay estimates from observed passenger outcomes.
- Conduct live checks and actual-trip validation.
- Build the origin/destination interface and display the recommended route, alternatives, total time, walking, transfers, and uncertainty.

**Deliverable:** a usable, evaluated prototype with a clearly stated service area and supported detour types.

## Work sequence

Steps 1-2 (routing) and Steps 3-4 (data and modeling) can progress in parallel. They come together in Step 5, followed by integrated evaluation and interface work in Step 6.

The first routing milestone is an automatic query that returns feasible alternatives using different nearby boarding stations. Model training does not need to be complete for this milestone.

## Repository organization

- `algo/`: routing, feature engineering, model training, evaluation, and their documentation.
- `data/`: dataset documentation, manifests, and data organization.
- Repository-wide language and project conventions are recorded in [AGENTS.md](../AGENTS.md).

## References

- [MTA developer resources](https://www.mta.info/developers)
- [OpenTripPlanner setup](https://docs.opentripplanner.org/en/latest/Basic-Tutorial/)
- [OpenTripPlanner routing configuration](https://docs.opentripplanner.org/en/latest/RouteRequest/)
- [Subway Data NYC](https://subwaydata.nyc/)
