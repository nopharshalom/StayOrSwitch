# October profile horizons and interpretation

This is a separate descriptive supplement. It does not modify any sealed profile, source, evaluation setting, or original report. The source covers October 1–31, 2026; all table values below use the existing full-month descriptive artifact.

Source: `data/processed/october/profiles-month.json.gz`. SHA256: `74ddd37dcb7bd3036a33bc7eb26173e57d146a94cdcc28809c7a6dd0cb9f86a3`.

Errors compare an earlier MTA endpoint arrival forecast with its quality-screened final MTA prediction proxy. They are not verified physical arrivals or door-to-door journey averages. Mean signed error can correct an endpoint forecast; mean positive delay averages `max(error, 0)` over all usable events and must not be added as a second correction. P90 is an empirical error percentile, not a calibrated prediction interval.

## Shorter-horizon direct components

F uses Court Sq–23 St → Jay St–MetroTech; G uses Court Sq → Hoyt–Schermerhorn. Each cohort retains the same 15–30 minute forecast horizon.

| Segment | Forecast horizon | New York weekday period | Usable events | Days | Mean signed error, min | Mean positive delay, min | P90 error, min | Unknown labels |
|---|---|---|---:|---:|---:|---:|---:|---:|
| F F09S → A41S | 15–30 min | Morning 06–10 | 860 | 22 | 2.79 | 2.90 | 5.62 | 106/969 (10.9%) |
| F F09S → A41S | 15–30 min | Midday 11–14 | 445 | 22 | 2.24 | 2.37 | 5.43 | 89/539 (16.5%) |
| F F09S → A41S | 15–30 min | Evening 16–20 | 810 | 22 | 3.68 | 3.72 | 6.95 | 78/897 (8.7%) |
| G G22S → A42S | 15–30 min | Morning 06–10 | 566 | 22 | 1.31 | 1.45 | 3.02 | 97/684 (14.2%) |
| G G22S → A42S | 15–30 min | Midday 11–14 | 478 | 22 | 1.74 | 1.81 | 3.53 | 46/524 (8.8%) |
| G G22S → A42S | 15–30 min | Evening 16–20 | 622 | 22 | 1.65 | 1.73 | 3.55 | 59/689 (8.6%) |

## Why the longer R component needs another horizon

R from Queens Plaza to Jay St–MetroTech often has more than 30 minutes of forecast travel remaining even before any waiting. These profiles require boarding to remain in the future. Therefore a 15–30 minute arrival cohort can contain almost no usable R examples. This is a forecast-window restriction, not evidence that the route or its historical records are generally unavailable. Do not interpret one-event cells as stable route averages.

The already-fitted 30–60 minute cohorts below expose the relevant longer-horizon evidence. They cannot be directly ranked against the F/G table as complete journey durations, because both horizon and subway component differ. No fitting or threshold has changed.

| Segment | Forecast horizon | New York weekday period | Usable events | Days | Mean signed error, min | Mean positive delay, min | P90 error, min | Unknown labels |
|---|---|---|---:|---:|---:|---:|---:|---:|
| R G21S → R29S | 15–30 min | Morning 06–10 | 1 | 1 | 1.38 | 1.38 | 1.38 | 0/4 (0.0%) |
| R G21S → R29S | 15–30 min | Midday 11–14 | 0 | 0 | unavailable | unavailable | unavailable | no forecast events |
| R G21S → R29S | 15–30 min | Evening 16–20 | 1 | 1 | 2.98 | 2.98 | 2.98 | 0/1 (0.0%) |
| R G21S → R29S | 30–60 min | Morning 06–10 | 703 | 22 | 1.80 | 2.16 | 5.42 | 56/766 (7.3%) |
| R G21S → R29S | 30–60 min | Midday 11–14 | 497 | 22 | 2.82 | 3.20 | 8.72 | 45/550 (8.2%) |
| R G21S → R29S | 30–60 min | Evening 16–20 | 599 | 22 | 1.79 | 2.35 | 5.46 | 111/719 (15.4%) |

The R transfer component from Herald Sq to Jay St is also retained separately:

| Segment | Forecast horizon | New York weekday period | Usable events | Days | Mean signed error, min | Mean positive delay, min | P90 error, min | Unknown labels |
|---|---|---|---:|---:|---:|---:|---:|---:|
| R R17S → R29S | 30–60 min | Morning 06–10 | 728 | 22 | 1.69 | 2.09 | 5.28 | 59/787 (7.5%) |
| R R17S → R29S | 30–60 min | Midday 11–14 | 521 | 22 | 2.81 | 3.18 | 8.80 | 46/567 (8.1%) |
| R R17S → R29S | 30–60 min | Evening 16–20 | 638 | 22 | 1.86 | 2.40 | 5.66 | 115/753 (15.3%) |

## Scope of the predictive artifact

The frozen predictive profile uses October 1–17 only and has seal `4e9b8374047d17a86f4d336d187078c873a36f8b6e2b032e2cff82e151cee035`. The full-month artifact above is descriptive and is rejected by `ProfileEstimator` for prediction.

Only 8 severe-context groups in the training artifact satisfy both 20 independent component events and three definitely applicable severe publisher families. They are broad A-line A27S → A41S groups pooling time periods and causes; five use fresh evidence and three use last-observed evidence. F/G and other sparse severe groups explicitly fall back to time-conditioned profiles or unchanged MTA estimates. This support count does not establish Switch success.

Unknown-label fractions use all independent forecast events in the same time group, before quality exclusion. Other excluded forecasts can have known labels but fail chronology or boarding checks. Events and days describe usable cohort support; repeated feed updates do not count as additional independent endpoint events.

See [the main monthly profile report](profiles.md) for other configured route components, separate Saturday/Sunday tables, and the complete interpretation notes. The JSON artifacts retain every configured horizon.
