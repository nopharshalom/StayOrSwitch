# Raw-source audit of large weekday peak ETA errors

The three inspected cells retain their original values. All 22 usable journeys
and 44 required boarding/alighting endpoints match the original CSV journals,
exact route/service/train identities and archived confirmation receipts.
Required endpoint timestamps are at most 30 seconds from their last observation;
stop-removal gaps are at most 15 seconds. Every raw trip has zero schedule
changes and zero schedule rewrites. Both one-alias and two-alias normalized
identities preserve the same physical train; each cell contains distinct trains.

| Corridor and period | Usable / scheduled | Distinct trains | Mean positive error, min | Median signed error, min | Largest error, min |
|---|---:|---:|---:|---:|---:|
| Hayden F, November 12 midday | 8 / 12 | 8 | 16.92 | 13.02 | 35.85 |
| Port Authority A, November 2 midday | 9 / 12 | 9 | 14.77 | 12.98 | 33.48 |
| Hayden F, November 13 evening | 5 / 16 | 5 | 12.59 | 2.73 | 51.43 |

All inspected errors are positive, so signed and positive-only means coincide
in these three cells. The November 13 evening mean is particularly sensitive
to one 51.43-minute selected-train error: the other four usable journeys average
2.88 minutes. That large observation is retained, and the five-of-sixteen
coverage remains explicit. It should not be presented as a typical evening
delay for all departures.

The largest error in each cell was also checked against its exact original
GTFS-realtime payload. The latest available capture, payload hash, descriptor,
explicit boarding-departure prediction and explicit destination-arrival
prediction all match the frozen input. Arrival and departure at A41S are equal
in all three raw forecasts, and A41S is followed by 18–20 additional stop
updates. The inspected forecasts therefore do not substitute departure for a
missing arrival or compare terminal dwell with a destination arrival.

These checks support the reported difference between earlier MTA predictions
and later final-prediction journal values. They do not independently establish
physical arrival times or the incident cause. The exact forecast-selected
train remains the evaluated journey; a passenger staying on the same line may
choose another earlier train. This was an outcome-selected quality audit,
not new independent performance evidence, and no cohort, prediction, label,
threshold or result was altered.

Evidence: [raw endpoint audit](november-weekday-large-peak-raw-audit.json)
and [raw forecast audit](november-weekday-large-peak-forecast-audit.json).
Reproduction scripts are `data/scripts/audit_november_large_peak_endpoints.py`
and `data/scripts/audit_november_large_peak_forecasts.py`.
