# Full October training for November analysis

The user authorized a separate model fitted to October 1–31, 2026. The original
October 1–17 experimental model, its held-out results, and the descriptive
monthly profile remain unchanged. This does not restore the superseded November
tree-model experiment.

The new model keeps the original feature hierarchy, component scope, event
weighting, minimum support thresholds and ETA correction semantics. It refits
from the sealed October representative-observation archive. That archive was
written before split-specific eligibility exclusions and includes all 31 dates.
Every row is reassigned to the new training split, then the existing training
eligibility rules are applied again. The monthly descriptive aggregate is not
renamed or promoted into a prediction model.

Training labels must be confirmed strictly before November 1 at 00:00 New York
time, which is November 1 at 04:00 UTC. Physical trains crossing into November
are purged. Unplanned disruption/severe publisher families observed on both
sides are purged, including a family that disappears and later recurs. This
uses November 1–18 input-only trip and alert inventories; no November outcome
label or performance result is read during fitting. Consequently this artifact
is a full-month training model with evaluation-input overlap purging, rather
than a claim that an October 31 deployment knew future incident membership.

The user's later reporting restriction selects the 13 weekdays within November
1–18. It does not change this full-October training run or its conservative
input-overlap purge, which still considers all 18 input dates, including weekends.

```sh
PYTHONPATH=.:algo .venv/bin/python data/scripts/build_full_october_profiles.py
```

The command refuses to overwrite its new completed outputs. It verifies the
original observation manifest and source hashes, preserves old experiment
hashes, streams the existing observations into temporary aggregate tables, then
seals a new `fit_split="train"` profile. The existing `ProfileEstimator` accepts
that artifact without weakening its rejection of descriptive profiles.

Outputs:

- `data/artifacts/october-2026-profiles-full-train.json.gz`
- `data/artifacts/october-2026-profiles-full-train.manifest.json`
- `data/manifests/full-october-fit-frozen.json`
- `data/reports/full-october-fit.json`
- `data/reports/full-october-fit.md`

The source observations contain 18 configured route/segment variants. Later
five-corridor alternatives may have endpoints absent from that original scope.
The report inventories exact-component coverage and route-level fallback
support for every supplied path leg. A supported route-wide group is not
evidence that the exact new segment was learned, and support still depends on
forecast horizon and the other query conditions.

Outcomes remain quality-screened final MTA prediction proxies. Positive-only
delay, signed ETA error and conditional late-only delay remain different
statistics. Repeated feeds do not create additional independent physical
endpoint events within a profile group.

Training retains the original October label-quality screen. Any newly declared
stricter November outcome-recency check belongs to evaluation and does not imply
that the same additional filter was retrospectively applied during fitting.

Incident counts identify publisher incident families. Several publisher IDs can
describe the same underlying disruption, so the three-family severe-support
threshold does not prove three causally independent disruptions. Likewise,
cross-window purging establishes separation for the recorded physical train
identities and publisher families; it does not prove that every shared physical
cause has been identified across differently named notices.
