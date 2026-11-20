# Pre-evaluation identity correction

The first complete source audit found 9,822 endpoint records flagged solely or
partly by the raw trip-ID route-prefix guard: 6,885 for actual W, 2,841 for 7X,
and 96 for FX. These are endpoint records, not independent trains or incidents.
W can use an N prefix; express trains can use either their own prefix or the
base-line prefix. The original guard incorrectly rejected valid forms.

The corrected rule accepts the actual route's own prefix and only these
additional aliases: W <- N, FX <- F, and 7X <- 7. Exact journal actual-route,
service/date/direction, schedule-change and cross-route identity checks remain.
Actual N and W identities are not merged into one event.

This is a source-identity correction before evaluation. The interrupted full
profile run had completed only October 1 extraction and started October 2.
No full-run training profile was fitted or sealed, no non-development delay-error
aggregates were computed, and no validation/test replay outcomes or selection
artifacts were produced. Source preparation had necessarily read the journals
to construct labels and identity/quality counts; the revision was prompted by
those identity checks, not prediction scores. Recommendation thresholds,
reference policy, time windows, route
templates and evaluation criteria are unchanged.

The original protocol is preserved in
`october-protocol-before-identity-fix.json`. Source preparation retains original
daily normalization producer fingerprints and byte-identical snapshots, alerts,
trip inventories and receipt indexes. A verified label-only rebuild archives the
previous source manifest/report and records new label-producer provenance.
Interrupted development diagnostics remain local and are referenced by
`data/reports/profiles-interrupted.json`.

The label-only rebuild passed all daily and merged-label parity checks in
139.28 seconds. All 221 retained inputs/normalization artifacts were unchanged.
Endpoint record count (196,024), receipt confirmations (183,493), timestamps,
identities and every other quality flag stayed unchanged.

| Measure | Before | After |
|---|---:|---:|
| Incorrect raw-prefix flags | 9,822 | 0 |
| Usable arrival records | 158,660 | 167,216 |
| Usable departure records | 155,438 | 163,679 |

The renewed active protocol was created before restarting the full profile build
at 2026-11-20 00:43:15 UTC. Its only code-hash differences are the label helper,
the new label-rebuild entrypoint and the evaluator entrypoint's producer-hash
list. Configuration, prediction and scoring modules are unchanged. Formal
evaluation remains gated on the new training-profile and evaluation seals.

The one-time migration command was:

```sh
PYTHONPATH=.:algo .venv/bin/python data/scripts/rebuild_october_labels.py
```

Fresh source preparation already uses the corrected helper. The migration
requires the original producer delta and should not be rerun against an already
corrected manifest. See `data/reports/october-source-verification.json` and its
archived origin-manifest references for executed lineage.
