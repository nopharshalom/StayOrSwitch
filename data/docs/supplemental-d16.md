# Supplemental Bryant Park endpoint labels

This is the retained initial attempt. For the current pre-incident experiment,
use the [extended raw-input projection and corrected labels](preincident-inputs.md).
The initial attempt cannot restore D16 observations omitted by the original
projection after a train passed the original Court Square boarding stop.

The pre-incident route experiment includes F service from Court Sq–23 St to
42 St–Bryant Pk. This is a plausible alternative to 7 and E service for a
Court Square to Times Square journey. The original October projection retained
the ordered intermediate F stops, but the original outcome configuration did
not request a D16S label. This supplement adds that endpoint in a separate file.

The official [MTA Subway Stations record](https://data.ny.gov/resource/39hk-dx4f.json?gtfs_stop_id=D16)
identifies D16 as 42 St–Bryant Pk, at 40.754222, -73.984569, with the south
direction labeled Downtown. Actual historical availability still comes from
each selected train's ordered stop updates. A normal station service listing
does not establish that every October train stopped there.

Run from the repository root:

```sh
.venv/bin/python data/scripts/prepare_supplemental_d16_labels.py
```

The command reads October 24–31 normalized snapshots for actual D16S
observations. October 24 provides boundary train observations; evaluation
remains October 25–31. It merges the full-month original trip identity inventory
and receipt index, retains cross-service-date and cross-route collision checks,
and calls the unchanged original label builder with the original service-date
journal windows. It never modifies the original source, labels, configuration,
profiles or reports. All source hashes are verified before and after the run.

Outputs:

- `data/processed/october-supplemental-d16/labels.json.gz`: only D16S outcomes,
  with the original `trip_id -> stop_id -> endpoint record` schema.
- `data/processed/october-supplemental-d16/label-quality.json`: local quality
  counts, kept separate from input-only experimental selection.
- `data/manifests/october-supplemental-d16.json`: source, producer, station
  metadata and output provenance.

After the experiment's input selection is frozen, callers may load and merge
these endpoints without changing any existing endpoint:

```python
from data.october.sources import read_labels
from data.supplemental_endpoints import merge_endpoint_labels

extra = read_labels("data/processed/october-supplemental-d16/labels.json.gz")
combined = merge_endpoint_labels(original_labels, extra, "D16S")
```

The merge returns a copy and rejects any unexpected stop or attempt to
overwrite an existing D16S endpoint. Only the evaluator reads these outcomes;
they are not supplied to route selection or historical profile fitting.
Existing profile coverage for the new F segment must remain explicit rather
than silently refitting profiles on the test week.

These labels remain screened final MTA prediction proxies, not independently
measured passenger arrivals. All original quality flags, schedule-change
exclusions, disappearance checks, and receipt-confirmation semantics remain.
