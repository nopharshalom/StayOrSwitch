# November weekday commuter advice coverage

The same 2,562 checkpoints, 13 weekdays, five corridors and 10% thresholds as the [previous replay](november-mixed-relative.md). All previously definite recommendations are reproduced. MONITOR means there is no supported change recommendation. It is counted separately from comparisons; both MONITOR and UNDETERMINED remain unresolved in the comparison coverage metric.

| Scope | Cases | Previous unresolved | Compared Stay | Switch | Monitor | No Stay ETA | Switch gain / tie / loss / unknown |
|---|---:|---:|---:|---:|---:|---:|---|
| All weekdays | 2562 | 1850 | 1722 | 288 | 460 | 92 | 39/42/46/161 |
| Earliest representatives | 205 | 130 | 154 | 20 | 25 | 6 | 2/5/4/9 |
| Severe | 274 | 204 | 205 | 40 | 29 | 0 | 2/2/5/31 |
| November 16–18 | 536 | 377 | 370 | 48 | 74 | 44 | 4/4/5/35 |
| courtsquare_timessquare | 156 | 62 | 123 | 31 | 2 | 0 | 5/4/2/20 |
| portauthority_tandon | 618 | 306 | 394 | 91 | 121 | 12 | 6/8/26/51 |
| grandcentral_boroughhall | 479 | 179 | 289 | 152 | 8 | 30 | 27/25/16/84 |
| kewgardens_tandon | 691 | 685 | 562 | 7 | 122 | 0 | 1/2/2/2 |
| inwood207_boroughhall | 618 | 618 | 354 | 7 | 207 | 50 | 0/3/0/4 |

## Outcomes of newly issued advice

| Recommendation | Alternative faster by >10% | Within ±10% | Alternative slower by >10% | Unknown |
|---|---:|---:|---:|---:|
| Switch | 8 | 7 | 11 | 46 |
| Stay | 34 | 158 | 389 | 645 |

The alternative for a new Stay is the fastest usable alternative in the decision-time forecast. A faster alternative in the Stay row is a missed opportunity.

## Remaining unresolved comparisons

| Reason | Cases |
|---|---:|
| ONLY_STAY_TIMED | 442 |
| SWITCH_NOT_CORROBORATED | 18 |
| NO_USABLE_STAY_ETA | 92 |

The frozen October 1–31 model and the two-minute boarding margin are used throughout. Positive savings must reach 10% of the forecast Stay duration for a Switch. An outcome is a gain or loss only when it falls outside ±10% of the reconstructed Stay duration. Added Switch advice requires the incident-profile and raw-MTA forecasts to agree on the same route. Both forecasts use the same underlying feeds.

Advice uses only information available at departure. Outcome durations use screened final MTA predictions and fixed walking assumptions. The long corridors use service problems on the previously reviewed common downstream segment. The November data had prior project exposure and checkpoints can repeat within one incident.

To reproduce from the existing mixed-corridor replay inputs, run the short, long and report stages of `algo/scripts/evaluate_commuter_coverage.py` in that order.
