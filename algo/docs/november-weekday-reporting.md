# Weekday reporting addendum

The user requested weekday-only reporting before any November outcome scoring.
This addendum changes the primary reporting population, not the running model
fit, the fixed five corridor paths, predictions, thresholds, or source quality.

Primary dates are November 2–6, 9–13, and 16–18, 2026: 13 Monday–Friday dates in
America/New_York. November 19 remains outcome boundary evidence only. The
October 1–31 model and its conservative November 1–18 input-only overlap purge
continue unchanged. All existing input freezes and producer hashes stay intact.

## Stay/Switch

- Retain the same input-qualified cohort and predictions. Select the weekday
  reporting view using local calendar dates only, without reading outcomes.
- Report all weekday checkpoints and the earliest weekday checkpoint per
  corridor/publisher incident family separately. Do not merely filter the old
  primary list: a family whose original representative was on a weekend can
  still contribute its first eligible weekday checkpoint.
- This view does not extend the original two-hour incident windows or create
  new cases. If no weekday checkpoint exists in the fixed cohort, that family
  has no primary weekday observation.
- Retain the November 16–18 subgroup, severe/closure qualifications, unknowns,
  missed selected trains, raw-policy comparisons and planned-context notes.
- Previously prepared all-date results may remain secondary audit artifacts;
  the user-facing headline and per-corridor tables use weekdays only.

## Peak ETA delays

- Filter the already-frozen departure grid by the same 13 local dates.
- The primary grid contains 2,860 checkpoints: 13 dates × 5 fixed Stay paths ×
  44 daily departure times. There are 195 daily corridor/period cells and 15
  pooled corridor/period cells.
- Retain morning 06:00–10:00, midday 11:00–14:00 and evening 16:00–20:00.
- Keep the same signed and positive-only means, outcome guards, coverage and
  pre-outcome physical-train representative definitions. Because these
  representatives are grouped by local date, filtering whole dates preserves
  the original representative selection.
- Deliver a weekday-only daily table, pooled table and 13-date heatmap. Keep
  the original 18-date grid and its reports as secondary audit evidence.

Bind `data/manifests/november-weekday-reporting.json` and this addendum in a new
reporting-view freeze before reading November outcome labels. Selection is
calendar-based and was requested after input coverage inspection, not after
seeing gains, losses or delay magnitudes. The inherited prediction/source
freezes remain authoritative for every selected record.
