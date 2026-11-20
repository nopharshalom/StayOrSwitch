# Pre-incident fastest-route delay replay

This is an exploratory, post-hoc search within October 25–31. The original predictor and development profiles are unchanged. The new Stay route is selected before the first problem, using only then-available feeds. It is fastest among the supplied alternatives, not a historical Google route or an exhaustive citywide optimum.

Origin: Court Square subway complex street entrance, Long Island City. Destination: Times Square, West 42nd Street at Seventh Avenue. Both comparisons start anew from the same origin; the person has not boarded. The interval between planning and reassessment is not added to the new journey duration.

Authored walking per candidate (seconds): `{"7_times_square": {"access_walk_seconds": 120, "egress_walk_seconds": 120, "transfer_walk_seconds": []}, "e_times_square": {"access_walk_seconds": 300, "egress_walk_seconds": 420, "transfer_walk_seconds": []}, "f_times_square": {"access_walk_seconds": 300, "egress_walk_seconds": 420, "transfer_walk_seconds": []}}`. These are research assumptions, including station access; all one-component +/-120-second sensitivities are retained, including whether the original fastest route remains fastest.

An anchor must precede the earlier of the first incident receipt and its initially declared active start, and its fastest route must have fresh NORMAL evidence. All supplied alternatives need complete timing and verified service evidence. Fixed lookbacks are 1/5/10/15/30 minutes. A baseline lead of three minutes or less is flagged as a near tie.

At reassessment the same route must carry an applicable official delay notice and its remaining MTA duration must increase by at least five minutes. Waiting and riding changes are separate. This does not prove causation: headways and train selection also change. Ordinary disruption is sufficient in this request, so the existing comparator uses require_severe=False; its five-minute Switch margin and three-minute outcome tie remain unchanged. A maintenance-related delay whose planning status is unspecified is not asserted to be unplanned.

Confirmed cases: **0**; distinct incident families: **0**.

| Mode | Scope | Switch | Scorable | Unknown | Gains >3 min | Ties | Losses >3 min |
|---|---|---:|---:|---:|---:|---:|---:|
| mta | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 |
| mta | conditional_timing_decision | 0 | 0 | 0 | 0 | 0 | 0 |
| time_profile | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 |
| time_profile | conditional_timing_decision | 0 | 0 | 0 | 0 | 0 | 0 |
| incident_profile | strict_decision | 0 | 0 | 0 | 0 | 0 | 0 |
| incident_profile | conditional_timing_decision | 0 | 0 | 0 | 0 | 0 | 0 |

Forecast-best alternative compared with Stay regardless of the issued decision:

| Mode | Comparable | Gain >3 min | Tie | Loss >3 min | Unknown | Gain missed by strict STAY |
|---|---:|---:|---:|---:|---:|---:|
| mta | 0 | 0 | 0 | 0 | 0 | 0 |
| time_profile | 0 | 0 | 0 | 0 | 0 | 0 |
| incident_profile | 0 | 0 | 0 | 0 | 0 | 0 |

Cases within an incident are correlated. Unknowns and missed selected trains are not successes. Scored arrival times are screened final MTA prediction proxies plus authored walks, not independently observed passenger arrivals.

## Case illustrations

The report retains the first input-qualified case per incident, plus the earliest comparable incident-profile Stay versus forecast-best alternative per incident, regardless of action or winner. The latter are explicitly outcome-selected illustrations and do not define the evaluation population.

## Coverage and limitations

The case table compares Stay with the forecast-best alternative even when the algorithm says STAY. This is a counterfactual diagnostic, not a recommendation to switch. JSON separately records the best alternative known from later outcomes and missed-opportunity counts; hindsight never selects a recommendation or the evaluation cohort.

Input selection rejections and every pre-problem anchor attempt are preserved in the prepared artifact and candidate-selection report. Official route/direction qualification is separate from the original classifier; planned work, opposite directions and narrow notices beyond the traversed segment are excluded.

New segments outside the frozen training groups explicitly fall back; existing component segments retain development-only profiles. Supplemental endpoint outcomes, when needed, use unchanged original quality rules. No new regressor is trained.

Full cases: `algo/local/october-preincident/scored-cases.json.gz` (SHA256 `64406e753d82e11c6bd63d1d04bb6aa083eefa0a46949bbfce994d556b989f0f`).
