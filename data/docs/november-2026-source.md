# November 2026 follow-up source package

This is a new source package covering November 1–19 for the authorized
November 1–18 analysis of the five previously selected corridors. November 19
is retained only as outcome boundary evidence. It preserves the October experiment,
training artifact, configuration, source manifests and normalized files.

The source is [Subway Data NYC](https://subwaydata.nyc/), derived from MTA
realtime feeds. On November 20, 2026 the publisher reported November 19 as the
latest available date, with a November 20 06:54 EST update. Acquisition verifies
the actual daily archives rather than relying only on that homepage statement.

## Reproduction

```sh
PYTHONPATH=.:algo .venv/bin/python data/scripts/prepare_november_2026.py --inputs-only --workers 4
PYTHONPATH=.:algo .venv/bin/python data/scripts/freeze_november_2026_inputs.py
PYTHONPATH=.:algo .venv/bin/python data/scripts/prepare_november_2026.py --labels-only
```

The first stage publishes `data/manifests/november-2026.json` with
`stage=INPUTS_PREPARED`, allowing input-only incident discovery, cross-month
train/incident purging, and forecast freezing before any evaluation outcomes
are read. The second stage constructs separate labels and updates the manifest
to `PREPARED`. It does not change daily snapshots or alert inventories.
The intermediate freeze command preserves the exact input-only manifest as
`data/manifests/november-2026-inputs.json`. It refuses to overwrite different
bytes or include labels, so concurrent consumers can hash a stable input source
while the main manifest advances to the completed label stage.

The configuration is `data/config/november-2026.json`. Acquisition records URLs,
resolved URLs, timestamps, exact hashes and sizes in
`data/manifests/november-2026-acquisition.json`. Complete raw archives stay in
ignored `data/raw/november-2026/`; already verified October raw archives are
referenced at their existing paths instead of copied. Normalized outputs stay
in ignored `data/processed/november-2026/`.

Each daily source emits the same snapshot, alert, trip and receipt interfaces
as the October implementation. The projection includes all five train-feed
groups and the union of all declared legs from the existing five-corridor
candidate sets. Every dedicated alert capture is retained. Train sampling and
metadata, full ordered configured spans, intermediate stop status, raw hashes,
trip aliases and source receipt evidence preserve the reviewed October rules.

## Boundaries and interpretation

- The formal decision window is November 1–18 inclusive in `America/New_York`,
  recorded in `data/manifests/november-analysis-window.json`. The user narrowed
  the window during source normalization. The frozen preparation configuration
  and source files retain November 1–19 coverage; source date fields (including
  original `decision_dates` wording) must be interpreted as preparation scope,
  subject to the separate analysis-window policy.
- November 19 contributes only following-day receipts and endpoint evidence for
  earlier selected journeys. It contributes no decision checkpoints, peak
  summaries, exposure denominators or held-out incident/trip purge membership.
- October 31 is separately marked input carry, not November exposure. It is
  normalized into the new directory using the expanded union projection.
- October 30 and 31 journals are boundary evidence only.
- November 20 CSV is optional because the archive may not yet be available.
  Acquisition records its status and exact failure, if any. Missing following
  evidence does not invalidate the available November dates; incomplete late
  endpoints remain unavailable rather than receiving invented confirmation.
  November 20 is not needed to complete the formal November 1–18 decision window.
- November 1 has 25 local hours. Absolute UTC instants distinguish the repeated
  01:00–02:00 hour. Source service identities retain their publisher-defined UTC
  interpretation and are not converted into local departure timestamps.
- Labels remain screened final MTA prediction proxies, separate from query-time
  snapshots. They are not independently measured passenger arrival times.
- `confirmed_at` requires an actual later same-feed collector receipt. Daily
  data completeness does not imply that every route or endpoint is usable.
- Alert archives preserve changed content. A last-observed alert is not evidence
  of a recent unchanged fetch; missing/unknown service state remains explicit.
- Stream ordering is chronological within each feed, not globally sorted.

Run boundary and projection checks with:

```sh
PYTHONPATH=.:algo .venv/bin/python -m unittest data.tests.test_november_2026 data.tests.test_november_input_freeze data.tests.test_october_sources data.tests.test_october_labels
```

The wrapper hashes its own producers and reused source modules before
processing and verifies them again before publishing completed sources. The
full fit and evaluation use their own independent manifests and freezes.

## Completed source preparation

All 41 required archives were verified, totaling 1,485,376,912 bytes including
four already-present raw archives reused by reference. The optional November 20
CSV URL returned HTTP 404. All 20 source days were normalized: October 31 carry,
November 1–18 analysis dates, and November 19 outcome boundary.

| Scope | Source snapshots | Dedicated alert captures | Raw train receipts |
|---|---:|---:|---:|
| Formal November 1–18 window | 134,287 | 4,253 | 1,330,517 |

These are source records, not independent trips, incidents or evaluation cases.
The full prepared package (including boundary days and normalized aliases)
contains 176,685 endpoint label rows, with 152,150 usable arrival rows and
148,694 usable departure rows under the unchanged source-label rules. Downstream
analyses apply their additional confirmation, age and selected-journey checks;
these broad source counts are not their success-rate denominators.

The separate label construction took 224.92 seconds after normalization.
Detailed provenance is in the acquisition, stable input, completed source and
independent source-audit manifests under `data/manifests/`.
