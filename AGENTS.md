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
- Place routing and prediction development under `algo/` and dataset documentation and organization under `data/`.

## Routing and prediction direction

- Users supply an origin, destination, and departure time.
- Generate candidate subway-and-walking routes automatically, including nearby alternative boarding and alighting stations and feasible detours.
- Combine a model trained on historical delay data with current MTA conditions to compare complete journeys.
- Follow the planned implementation sequence in [algo/README.md](algo/README.md).
