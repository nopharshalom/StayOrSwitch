# Project Memory

## Project context

- Course: TECH 5900, Fall 2026.
- Project question: **How might we improve getting around New York City?**
- Use this question as the context for course and project analyses unless the user updates it.

## Repository conventions

- The canonical project repository is https://github.com/nopharshalom/StayOrSwitch.
- Keep StayOrSwitch project code in this repository.
- Write all code in English throughout the repository, including identifiers, comments, docstrings, log and error messages, and test descriptions.
- Write new project documentation in English as well.
- The user explicitly requested the repository location and English-language code convention on 2026-11-19.
- Place ETA prediction and Stay/Switch algorithm development under `algo/`. Keep data source files, downloaders, processing code, data tests, manifests, and dataset documentation under `data/`, as explicitly requested on 2026-11-19. Keep large raw and processed artifacts out of Git and record their local paths and checksums.

## ETA prediction and decision scope

- StayOrSwitch is a decision companion, not a navigation app. The user clarified this scope on 2026-11-19.
- Google Routes or another external provider supplies the current itinerary and candidate alternatives. Do not build an OTP routing engine or navigation UI for this version.
- Our algorithm combines historical delay patterns and current MTA conditions to re-estimate destination arrival times, especially during delays, and compare the current itinerary with available alternatives.
- The teammate owns final UI design and app development. Deliver the algorithm, an evaluation API, and English integration materials.
- First-version user state: not yet on a train, departing now. Modes: subway and walking.
- Pilot origin: Hayden LIC Apartments by Rockrose, 43-25 Hunter Street, Long Island City, NY 11101.
- Pilot destination: NYU Tandon School of Engineering, 6 MetroTech Center, Brooklyn, NY 11201. Verify entrance coordinates before door-to-door evaluation.
- Historical pilot data: Subway Data NYC, expanded to 2026-11-02 through 2026-11-15 inclusive on 2026-11-19, using America/New_York service dates. Distinguish calendar-day source archives from trip service dates. Process a weekday and a weekend sample before the full window. Report weekday, Saturday, and Sunday coverage and evaluation separately; two weekends do not establish general weekend performance.
- Rank feasible supplied candidates by estimated total door-to-door time. Do not impose arbitrary walking, transfer, or detour limits or penalties; actual walking and transfer times still count.
- Keep the selected current itinerary as the Stay reference. Do not substitute the provider's newly preferred route for that reference. Without a reference itinerary, do not invent a Stay/Switch decision.
- A train-arrival ETA is not the final destination ETA. Do not blindly add an MTA-trained residual to a route provider's total ETA or claim inferred arrival labels are physical ground truth.
- Follow the seven-step development plan in [algo/README.md](algo/README.md): contract, live-data integration, historical data, baseline comparator, model training, evaluation API integration, and validation/handoff.
- Step 1 artifacts live in `algo/contracts/`, `algo/docs/`, and `algo/examples/`. Use the version 1.0 contract for integration work; examples are explicitly simulated, and no live API/model is delivered by Step 1.
- Step 2 implementation lives in `algo/stayorswitch/` with commands and limitations in `algo/docs/live-integration.md`. It links provider routes to live MTA candidates; it does not calculate corrected destination ETAs or Stay/Switch decisions yet.
- Google Routes is the pilot provider. Keep its key only in ignored local configuration or environment variables. Development HTTP uses IPv4 to match the IP-restricted key; never log or commit credentials. Actual provider payloads are not test fixtures or historical model labels.
- Step 4 lives in `algo/stayorswitch/baseline.py`, with a command in `algo/scripts/run_baseline.py` and usage in `algo/docs/baseline.md`. It computes complete baseline journey ETAs and contract-compatible comparisons without a trained model or API server. Fresh supplied walking-only candidates may compete; provider-only transit fallbacks remain display-only. Never invent a current itinerary or treat absent trains as proof of route-wide infeasibility.
- Step 3 historical processing lives in `data/history/` and `data/scripts/build_history.py`, with scope in `data/config/pilot-history.json` and evidence in `data/manifests/` and `data/reports/`. The initial dataset samples five train feed groups every 60 seconds for 33 pilot stations and joins archived alerts as of each decision. Dataset scope is not a live routing restriction. CSV UIDs are opaque UTC-based join keys, not physical departure times. Use final global-integrity counts and select both the training split and eligible labels before fitting any model; held-out dates remain held out.
