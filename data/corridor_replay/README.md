# Historical corridor replay data

This diagnostic replays fixed Court Square F and G paths for the Hayden LIC to
NYU Tandon pilot. It does not reconstruct historical Google Routes results and
does not train or tune a model. Route templates, fixed walking assumptions, and
the unchanged-model policy are in `data/config/corridor-replay.json`.

| Fixed supplied path | Boarding stop | Alighting stop | Access walk | Egress walk |
| --- | --- | --- | --- | --- |
| F: Court Sq–23 St → Jay St–MetroTech | F09S | A41S | 300 seconds | 300 seconds |
| G: Court Sq → Hoyt–Schermerhorn Sts | G22S | A42S | 240 seconds | 720 seconds |

These two direct paths are a bounded experiment, not an exhaustive set of
alternatives. Historical raw trip stop order must establish availability.

Run discovery and preparation from the repository root:

```sh
.venv/bin/python data/scripts/scout_corridor_replay.py
.venv/bin/python data/scripts/prepare_corridor_replay.py
PYTHONPATH=algo:data .venv/bin/python -m unittest data.tests.test_corridor_replay
```

## Retrospective discovery

The discovery script examines November 12–15, 2026, between 06:00 and 23:00
America/New_York in the existing historical arrival and segment shards. These
dates were already opened for the frozen-model evaluation; this diagnostic is
not a new untouched test set.

G discovery joins the same train's Court Square departure and Hoyt–Schermerhorn
arrival forecasts at the same capture. It first chooses the earliest predicted
destination arrival that can be boarded after the fixed access walk, then uses
quality-screened journal outcomes to find forecast errors of at least 300
seconds. Either a departure or destination error can enter this initial pool.

F has a discovery coverage limitation: a typical F09S–A41S ride takes about 27
minutes, so a five-minute access walk places the destination outside the
original processed features' 30-minute horizon. Supplementary F discovery uses
the earliest catchable F09S departure and a departure forecast error of at least
300 seconds. Missing destination discovery fields remain null. This does not
establish that F had no other destination delays.

`scout-primary.json` retains the discovery denominator and every qualifying
cutoff. Preparation uses all 140 discovered cutoffs before any episode spacing.
`scout-primary-pool.json` provides an additional small chronological per-route
pool, which is not the raw replay input. Model predictions, Switch results, and alternative outcome
advantages are never used in discovery. The evaluator must subsequently rank
both paths from complete raw as-of forecasts, fix the unmodified-MTA fastest
path as the reference, and check its destination proxy error. The 300-second
diagnostic threshold is not a production switching threshold. Large residuals
are flagged for review, not discarded solely because of magnitude.

## Snapshot and outcome separation

Preparation verifies original archive sizes and SHA256 digests, then reads
archived payloads directly. It chooses the latest collector timestamp at or
before each decision for each feed. Train captures must be within 180 seconds;
source freshness is checked separately. A latest invalid or conflicting
capture remains missing rather than reviving an older successful result.
Complete normalized stop updates are retained, including predictions more than
30 minutes away. Each selected snapshot records the archive member, collector
time, and payload SHA256.

The last archived alert payload is retained with its real capture time, even
when stale. The publisher's content deduplication does not prove a fresh
unchanged alert fetch. Missing or stale alert evidence therefore remains
visible to the evaluator's strict gate; a conditional timing ranking is not an
eligible Stay/Switch recommendation.

Later CSV journal outcomes live only in the bundle's separate `labels` map,
keyed by service-qualified normalized trip identity and stop ID. The existing
label validator verifies the opaque source UID, raw trip ID, route, schedule
history, stop-disappearance ordering, and observation gap. Arrival and departure
usability are explicit. All observed endpoint IDs are unioned across snapshots
so later snapshots cannot erase an earlier boarding outcome. Conflicting
identity metadata makes the outcome unusable. No labels are inserted into
as-of snapshots or model features.

The journal's final predictions are **MTA-derived outcome proxies**, not
independent observations of train movement or passenger arrival. A usable
proxy does not independently verify uninterrupted train identity during a
large disruption. Outcome comparisons must follow the same predicted-selected
train and reject a missed boarding or missing endpoint rather than substitute
a hindsight-selected train.

## Artifacts

- Ignored local bundle: `data/processed/corridor-replay/replay-bundle.json.gz`.
- Full discovery and small pool: `data/processed/corridor-replay/scout-primary*.json`.
- Source/input/output checksums: `data/manifests/corridor-replay.json`.
- Data coverage and freshness: `data/reports/corridor-replay-data.json`.
- Ranking, episode selection, walking sensitivity, and evaluation belong under
  `algo/`; see `algo/docs/corridor-replay.md`.

The original raw packages remain local path references. Preparation does not
copy them into Git or alter the frozen historical/model artifacts.
