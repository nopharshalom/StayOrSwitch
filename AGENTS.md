# Project Memory

## Context and conventions

- Course: TECH 5900, Fall 2026. Project question: **How might we improve getting around New York City?**
- Canonical repository: https://github.com/nopharshalom/StayOrSwitch.
- All repository code, comments, messages, tests, and new documentation use English.
- Put data acquisition, processing, incident extraction, historical statistics, data tests and manifests under `data/`; prediction, comparison, evaluation and interface materials under `algo/`.
- Keep credentials in ignored local configuration. Never print or commit keys or provider payloads as training fixtures.

## Current approved direction (November 19, 2026)

- Follow `algo/docs/october-implementation-plan.md`; it supersedes the old November model and two-route replay plan.
- The user explicitly requested deleting old model/data code, artifacts and results, and replacing them with this implementation. Do not restore those experiments as the active implementation. Git history does not need rewriting.
- Use the complete **October 1–31, 2026** Subway Data NYC archive in America/New_York. September 30 and November 1 journals are boundary evidence only.
- Development: October 1–17; validation: October 18–24; final test: October 25–31. Use full-month profiles only for description; predictive evaluation uses sealed development-only profiles and keeps train/incident boundaries separate.
- Cross-split incident purging targets families with any input-only unplanned DISRUPTION or SEVERE version, including their earlier unknown/recovery observations. Planned-only and unknown-only notices retain explicit context and may contribute time profiles; do not claim independent-incident generalization for them.
- Primary output: historical ETA underestimation for the relevant route segment/direction, weekday/Saturday/Sunday, time period (including morning, midday and evening), forecast distance and incident state. Report support and distributions, not just a single mean.
- Secondary output: meaningful Switch advice during applicable official severe service problems. Include multiple route families: F, G, R, E to A/C, 7 to 4/5, 7 to 2/3, and N/W to R; verify historical availability and transfers.
- Start with historical statistics and incident rules. Do not assume another trained regressor is needed. Small time differences are practically immaterial to the user.
- Initial plan parameters: predicted Switch saving at least 300 seconds; outcome differences within +/-180 seconds are ties. Keep recommendation and outcome thresholds distinct and freeze settings before final testing.

## Product and evidence boundaries

- StayOrSwitch is a decision companion, not a navigation app. External providers supply current/candidate itineraries; the teammate owns app UI and development.
- Initial state: not boarded, leaving now. Pilot: Hayden LIC Apartments, 43-25 Hunter Street, Long Island City -> NYU Tandon, 6 MetroTech Center, Brooklyn.
- Include access walking, waiting, riding, transfer walking/waiting and egress. Do not impose arbitrary walking, transfer or detour penalties. Walking assumptions in historical research must be labeled and tested.
- Live Stay means the user's selected itinerary. Historical replay uses the same-cutoff fastest unmodified MTA candidate as the reference, as requested by the user. No reference means no invented Stay/Switch decision.
- Use one information cutoff, preserve alert versions, and never backdate later severe wording or read future feeds to make a transfer catchable.
- Final MTA prediction journals are screened outcome proxies, not independent passenger observations. Missing or missed-boarding outcomes remain unknown, never successes or ties.
- Raw trip-ID prefixes are namespace hints. Accept the actual route's own prefix and the observed aliases W <- N, FX <- F, and 7X <- 7, while preserving exact journal actual-route, service/direction and cross-route collision checks. See the pre-evaluation identity correction record; do not reintroduce the rejected-prefix bug.
- Do not double-count delay already included in MTA ETA. Distinct line names do not establish independent disruption exposure.
- Data freshness and last-known reconstructed archive alerts are different. Unknown alerts are not normal service.
- Preserve reusable Google/MTA integration, baseline journey arithmetic, API contracts and UI materials while replacing the old modeling/data stack.
