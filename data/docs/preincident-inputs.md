# Extended input coverage for the pre-incident experiment

The original October projection preserves whole configured leg spans and global
endpoint updates. That is sufficient for the original journeys, but it does
not promise complete coverage for a new boarding stop after an original origin.
For example, a southbound F train may already have passed Court Square while
Bryant Park is still a catchable boarding stop. The old projection can omit
Bryant Park after Court Square disappears from the remaining stop updates.

This supplement reruns the unchanged normalizer on existing raw October 24–31
archives for BDFM and numbered feeds, retaining all original paths and adding:

- F/FX: Court Sq–23 St (`F09S`) to Bryant Park (`D16S`).
- F/FX: Bryant Park (`D16S`) to Jay St–MetroTech (`A41S`).
- 7/7X: Grand Central (`723S`) to Times Square (`725S`), including `724S`.

D16S is also retained as a global endpoint. Original route IDs, trip identities,
sampling interval, raw capture selection, label rules and training profiles do
not change. The new configuration is projection scope only; it is not a routing
recommendation or a change to the evaluated algorithm.

## Prepare and use

```sh
.venv/bin/python data/scripts/prepare_preincident_inputs.py
```

The completed manifest is `data/manifests/preincident-inputs.json`. Its `days`
entries use the same artifact structure as the original source manifest.
Snapshots remain under ignored `data/processed/preincident-inputs/`.

For each date, **replace** the original BDFM and numbered snapshots with the
supplement's corresponding records. Retain original ACE, other train feeds and
alerts. Do not append old and new copies of the same capture: that would create
ambiguous duplicate observations. The supplement also reproduces alerts only
to verify byte equality; those duplicates are not additional evidence.

The manifest verifies every selected capture's raw digest and metadata, every
retained trip descriptor and status, and all old stop values in their original
order. It also records actual raw examples whose post-Court-Square stop spans
are restored. The automatic example tags identify an absent original origin;
absence can also reflect a different stop pattern and alone does not prove
that the train previously called at Court Square. A passing claim requires
earlier observations of the same service-qualified train. The receipt records
and alerts match the original preparation.
All original source artifacts are hash-checked before and after processing.

## Separate outcome endpoints

Corrected D16S labels are at
`data/processed/preincident-inputs/d16-labels.json.gz`, bound by the manifest's
`labels` entry. These use the extended observed-stop inventory, the full-month
original train identity/collision inventory, all original receipt checks and
the unchanged journal-label builder. Existing endpoint labels remain unchanged.

Only after input-only case selection is frozen may the evaluator merge them:

```python
from data.october.sources import read_labels
from data.supplemental_endpoints import merge_endpoint_labels

combined = merge_endpoint_labels(
    original_labels,
    read_labels("data/processed/preincident-inputs/d16-labels.json.gz"),
    "D16S",
)
```

The earlier `october-supplemental-d16` artifacts remain as the superseded initial
attempt. They recovered D16 only where the old projection already retained it;
they do not establish complete new-route coverage. No earlier artifact is
overwritten. The experiment's revised input provenance must name this extended
manifest rather than silently treating the old data as complete.

These are still screened final MTA prediction proxies, not independently
observed passenger arrivals. Outcome quality counts remain separate from
input-only route and incident selection. No test-week outcome is used to fit
new historical profiles; unsupported new segments retain disclosed fallback.
