# Line 7 midday negative ETA error audit

The Court Square to Times Square midday result passes the raw-source spot
check. The negative mean is not an arrival/departure field mix-up or a
destination terminal-dwell comparison.

Across 156 weekday midday departure checkpoints, 74 have usable outcomes,
46 miss the exact forecast-selected train under inferred timings, and 36 lack
usable endpoints. Among the 74 usable outcomes, 67 errors are negative, one is
zero and six are positive. The signed mean is **-205.5 seconds (-3.425 minutes)**;
the mean positive error is **4.703 seconds (0.078 minutes)**.
The latter is not ETA accuracy: raw-MTA mean absolute error among those same
74 usable cases is **214.905 seconds (3.582 minutes)**. Coverage is **47.4%**;
unknown journeys are not assigned zero error.

The signed mean decomposes into **-208.824 seconds of boarding-departure
forecast error** and **+3.324 seconds of riding-duration error**. The available
cases primarily have earlier inferred boarding departures than the initial
MTA forecast; the ride itself contributes little to the mean difference.

Three diagnostic cases were selected after scoring: the two most negative
errors and a central negative case on another date. This is an outcome-selected
debugging sample, not additional performance evidence.

| Local departure | Boarding-departure error | Ride-duration error | Destination-arrival error |
|---|---:|---:|---:|
| November 9, 11:45 | -406 s | -4 s | -410 s |
| November 4, 11:30 | -304 s | +73 s | -231 s |
| November 2, 12:15 | -348 s | -37 s | -385 s |

The exact original protobuf payloads match selected **719S departure** and
**725S arrival** fields. The arrival forecast never substitutes destination
departure. Each raw forecast and final journal continues from 725S to 726S;
725S is not the final stop in these selected journeys. The final 725S dwell
is 20 seconds. Required boarding/alighting endpoint proxies have absolute
last-observed ages of 29–59 seconds and removal gaps of three seconds, with
confirmed archived receipts, exact trip identities and one normalized alias.

All three raw forecasts contain a 300-second predicted dwell at upstream
718S, before the boarding stop. This is consistent with conservative
pre-boarding forecasts, but the audit does not establish the physical cause
or actual upstream dwell. Those upstream endpoints are not used as outcomes.

The 36 unavailable cases include 25 with arrival-after-disappearance flags,
eight with departure-after-disappearance flags, three missing journals and
two with excessive endpoint observation age. These categories overlap. Their
exclusion and the 46 missed boardings mean the small positive-only mean must
remain conditional on the **74/156 usable journeys**, not a claim of uniformly
reliable or delay-free midday service.

The audit passed 156 raw-journal assertions and 33 raw-forecast assertions.
No inputs, labels, predictions, metrics or producer code changed. Exact payload
members, hashes, raw timestamps, identities and full-cohort arithmetic are in
the [audit JSON](november-weekday-seven-raw-audit.json).
