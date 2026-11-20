# November weekday replay with relative thresholds

Test dates: November 2–6, 9–13 and 16–18, 2026. Use the frozen October profile and a two-minute boarding margin. Recommend Switch at a predicted saving of at least 10% of that policy’s Stay duration. Score gains and losses strictly outside ±10% of the reconstructed Stay duration.

| Scope | Cases | Stay | Undetermined | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All weekdays | 2562 | 496 | 1850 | 216 | 31 | 35 | 35 | 115 |
| Earliest representatives | 205 | 55 | 130 | 20 | 2 | 5 | 4 | 9 |
| Qualified severe | 274 | 42 | 204 | 28 | 2 | 2 | 2 | 22 |
| November 16–18 | 536 | 125 | 377 | 34 | 4 | 3 | 4 | 23 |
| Three short corridors | 1253 | 496 | 547 | 210 | 30 | 33 | 34 | 113 |
| Two long corridors | 1309 | 0 | 1303 | 6 | 1 | 2 | 1 | 2 |
| courtsquare_timessquare | 156 | 70 | 62 | 24 | 3 | 3 | 2 | 16 |
| portauthority_tandon | 618 | 240 | 306 | 72 | 5 | 8 | 19 | 40 |
| grandcentral_boroughhall | 479 | 186 | 179 | 114 | 22 | 22 | 13 | 57 |
| kewgardens_tandon | 691 | 0 | 685 | 6 | 1 | 2 | 1 | 2 |
| inwood207_boroughhall | 618 | 0 | 618 | 0 | 0 | 0 | 0 | 0 |
| Raw MTA Stay / model Switch | 51 | 0 | 0 | 51 | 6 | 15 | 6 | 24 |
| Severe raw Stay / model Switch | 8 | 0 | 0 | 8 | 1 | 2 | 0 | 5 |
| Primary raw Stay / model Switch | 5 | 0 | 0 | 5 | 0 | 2 | 1 | 2 |
| Severe on long corridors | 165 | 0 | 163 | 2 | 1 | 0 | 0 | 1 |

## Forecast margin sensitivity

Keep the same ten-percent outcome threshold in both rows. Only the forecast threshold for issuing advice changes.

| Scope and forecast threshold | Cases | Stay | Undetermined | Switch | Gain | Tie | Loss | Unknown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All weekdays, 5 minutes | 2562 | 552 | 1850 | 160 | 23 | 24 | 23 | 90 |
| All weekdays, 10% | 2562 | 496 | 1850 | 216 | 31 | 35 | 35 | 115 |
| Three short corridors, 5 minutes | 1253 | 552 | 547 | 154 | 22 | 22 | 22 | 88 |
| Three short corridors, 10% | 1253 | 496 | 547 | 210 | 30 | 33 | 34 | 113 |
| Two long corridors, 5 minutes | 1309 | 0 | 1303 | 6 | 1 | 2 | 1 | 2 |
| Two long corridors, 10% | 1309 | 0 | 1303 | 6 | 1 | 2 | 1 | 2 |

The three short routes reuse frozen raw and corrected ETA predictions and feed-following outcomes. The long routes use archived Google paths and walks, original sampled train feeds, the same boarding-safe predictor and feed-following executor, screened journal endpoints and the same 300 km/h outcome sanity limit. The October profile uses its existing fallback groups when exact long segments lack training support.

The event cohort is matched: Kew Gardens uses reviewed southbound F notices from the previously tested downstream F path; Inwood uses reviewed southbound A notices from the Port Authority path. New upstream-only incidents are outside this cohort. Inwood and Port Authority can share an incident. Each earliest representative is per corridor and notice family. The weekday samples and thresholds have prior exposure. MTA final predictions and fixed walks are duration proxies. Unknowns remain in denominators.

Kew Gardens candidates include F, FX and E to R. Google also returned an E to A alternative with an unresolved transfer walk; this path is unavailable to the decision rule. Inwood includes A and 1 to 3. The strict decision rule may recommend a faster eligible alternative, but cannot assert Stay when a supplied alternative remains unassessed.

For example, at 10:42:48 New York time on November 2 in Inwood, the model found seven A candidates, six 1 candidates and one 3 candidate after transfer readiness. The captured 1-line service context was UNKNOWN while the 3-line context was NORMAL. The strict decision could not assess the alternate even though train timing was available.

With the earlier five-minute forecast threshold and the new 10% outcome band, the same cases give [2562, 552, 1850, 160, 23, 24, 23, 90] in the table column order.

Exact October training support covers 0 of 7 new route/segment pairs.
1 comparable Switch decisions depend on waiting until an updated feed despite a temporarily unverifiable intended departure.

## Long-corridor examples

- 2026-11-12T16:28:33.587000-05:00 · kewgardens_tandon · F (71.5 min) to FX (57.6 min), gain. [F] trains are running with severe delays in both directions while we remove water from the tracks at Jamaica-179 St. Take an [E] train and local buses.
- 2026-11-02T16:28:15.560000-05:00 · kewgardens_tandon · F (54.3 min) to FX (58.6 min), tie. [F] trains are running with delays in both directions while rerouted [M] trains share tracks.
- 2026-11-02T16:58:15.560000-05:00 · kewgardens_tandon · F (51.6 min) to FX (59.3 min), loss. [F] trains are running with delays in both directions while rerouted [M] trains share tracks.
- 2026-11-05T16:56:02.741000-05:00 · kewgardens_tandon · F (unknown) to FX (59.7 min), unknown. [E] trains are running with delays in both directions. Downtown [F] trains are running with delays.

## Reproduction

Use the existing raw November archives, Google captures and frozen October profile. Run from the repository root:

```sh
PYTHONPATH=algo:. .venv/bin/python -m data.november_mixed_routes
.venv/bin/python algo/scripts/evaluate_november_mixed_relative.py short
.venv/bin/python algo/scripts/evaluate_november_mixed_relative.py long
.venv/bin/python algo/scripts/evaluate_november_mixed_relative.py report
```
