# Additional Times Square R boarding evidence

The two added corridors keep the experiment at five total origins/destinations.
The current Google alternative from Port Authority to NYU Tandon includes R
from Times Sq (`R16S`) to Jay St–MetroTech (`R29S`). The earlier projection has
the alighting endpoint but does not retain every required boarding observation.

This separate supplement extends the NQRW projection with the R16S-to-R29S
span. It reads the existing October 24–31 raw archives directly, preserves all
earlier observations, and writes only new artifacts. October 24 is boundary
evidence; evaluation remains October 25–31. No training profiles are changed.
The new boarding endpoint does not create historical training support; prediction
uses the unchanged profile estimator's existing fallback when needed.

```sh
.venv/bin/python data/scripts/prepare_incremental_extra_inputs.py
```

The source manifest is `data/manifests/google-corridor-inputs.json`; the new
manifest is `data/manifests/incremental-extra-inputs.json`. Daily artifacts and
new labels are under ignored `data/processed/incremental-extra-inputs/`.

For each date, replace **only NQRW** with the new snapshots. Retain the preceding
Google supplement's numbered feed, the preincident supplement's BDFM feed, and
the original ACE, G and alert sources. Never append duplicate captures. The
manifest records source, configuration, producer and artifact hashes.

The completed preparation took 285.301 seconds. All 11,507 selected NQRW
captures across eight dates passed parity; 36,840 stop updates were added,
all at R16S. Nine focused tests cover configuration, preservation, mixed
alert/train streams and label merge guards. An independent
[input audit](../manifests/incremental-extra-inputs-audit.json) supplements the
producer's full parity check.

Parity checks require identical capture metadata, raw hashes, trip coverage,
trip order and descriptors, original stop values and order, vehicles, receipts
and alerts. The new span can add R16S and previously omitted intermediate stop
updates. It cannot change an earlier observation or introduce a new train.
The shared stop projection may also retain R16S updates on existing N/W trains;
the new outcome-label scope remains R only.

The labels artifact contains only newly observed **R / R16S** endpoint keys.
The existing receipt confirmation, service-qualified identity collision checks
and screened final MTA prediction rules are unchanged. Merge these additions
using `data.incremental_extra_inputs.merge_label_additions`; preserve all
original, D16S and earlier Google endpoint labels. Any overwrite is rejected,
even if the supplied value is identical.

Outcome labels are produced separately from input selection. The evaluation
opens them only after candidate paths, notice qualification and decision inputs
have been frozen. A missing or unreliable label remains unknown. These are
MTA final-prediction proxies, not independent passenger measurements.
