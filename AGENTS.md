# Project memory

- Course: TECH 5900, Fall 2026. The project question is **How might we improve getting around New York City?**
- The canonical repository is https://github.com/nopharshalom/StayOrSwitch. Write code, comments, tests and repository documentation in English.
- Keep acquisition, historical data preparation and evidence under `data/`. Keep prediction, comparison, evaluation and app contracts under `algo/`. Keep credentials and provider payloads local.
- The first algorithm serves passengers leaving now who have yet to board. Accept provider-supplied routes and an explicit Stay reference. Include access, transfers and egress walking. Use raw and historical ETA evidence with a conservative boarding margin.
- The primary experiment is the [November two-corridor replay](algo/reports/november-all-forecast-boarding-any-saving.md) with the frozen October 1–31, 2026 model. Preserve the cohort, as-of feed selection, and missing outcomes. The report records the boarding assumption, outcome thresholds and denominators.
- Keep the relative predicted Switch threshold separate from retrospective scoring. Judge savings from the perspective of the recommended action. Retain repeated decisions when they involve the same trains.
