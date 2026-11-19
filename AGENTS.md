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
- Place ETA prediction and Stay/Switch algorithm development under `algo/` and dataset documentation and organization under `data/`.

## ETA prediction and decision scope

- StayOrSwitch is a decision companion, not a navigation app. The user clarified this scope on 2026-11-19.
- Google Routes or another external provider supplies the current itinerary and candidate alternatives. Do not build an OTP routing engine or navigation UI for this version.
- Our algorithm combines historical delay patterns and current MTA conditions to re-estimate destination arrival times, especially during delays, and compare the current itinerary with available alternatives.
- The teammate owns final UI design and app development. Deliver the algorithm, an evaluation API, and English integration materials.
- First-version user state: not yet on a train, departing now. Modes: subway and walking.
- Pilot origin: Hayden LIC Apartments by Rockrose, 43-25 Hunter Street, Long Island City, NY 11101.
- Pilot destination: NYU Tandon School of Engineering, 6 MetroTech Center, Brooklyn, NY 11201. Verify entrance coordinates before door-to-door evaluation.
- Historical pilot data: Subway Data NYC, 2026-11-09 through 2026-11-15 inclusive, using America/New_York service dates.
- Rank feasible supplied candidates by estimated total door-to-door time. Do not impose arbitrary walking, transfer, or detour limits or penalties; actual walking and transfer times still count.
- Keep the selected current itinerary as the Stay reference. Do not substitute the provider's newly preferred route for that reference. Without a reference itinerary, do not invent a Stay/Switch decision.
- A train-arrival ETA is not the final destination ETA. Do not blindly add an MTA-trained residual to a route provider's total ETA or claim inferred arrival labels are physical ground truth.
- Follow the planned implementation sequence in [algo/README.md](algo/README.md).
