# Full October training for November analysis

The original October experimental model and all earlier results remain unchanged.

| Item | New model |
|---|---|
| Training dates | October 1–31, 2026, America/New_York |
| Outcome confirmation cutoff | Strictly before November 1, 00:00 EDT (04:00 UTC) |
| Boundary inventory | November 1–18 inputs only; no November outcomes used for fitting |
| Representative observations | 1,095,007 |
| Eligible observations | 870,415 |
| Aggregate groups | 33,091 |
| Supported rule-classified severe groups | 54 |
| Fitting elapsed seconds | 1886.4 |

Observations are not unique passengers or complete train trips. Each aggregate deduplicates physical endpoint events. Supported severe groups satisfy the existing event and incident thresholds; they are not evidence of successful Switch outcomes.

## Eligibility exclusions

| Reason | Representative observations |
|---|---:|
| INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY | 202 |
| OUTCOME_RECEIPT_NOT_CONFIRMED | 359 |
| TRAIN_CROSSES_DEVELOPMENT_BOUNDARY | 234 |
| unusable_observations | 223,797 |

## Components without direct training coverage

The five-corridor experiment keeps all approved alternatives. The following exact components were not in the original training projection. A route-wide fallback can be used only when its particular query group has sufficient support; otherwise MTA remains unchanged.

| Line | Segment | Supported route-wide time groups |
|---|---|---:|
| 6 | 631S → 635S | 0 |
| 7 | 723S → 724S | 9 |
| 7 | 723S → 725S | 9 |
| F | D16S → A41S | 8 |
| F | F09S → D16S | 8 |
| FX | D16S → A41S | 8 |
| R | R16S → R29S | 8 |
| R | R20S → R28S | 8 |

## Provenance and interpretation

- Artifact: `data/artifacts/october-2026-profiles-full-train.json.gz`.
- Artifact SHA256: `35f9a70a5045b7a5aa1e43e1e605b4517ab289561ca2bcc86a2de69d4519834a`.
- Content seal: `f94de920d9ed5bac980b5a7423f6b9096732781eb78d4bb1bd5b64203ba0b9a5`.
- Reusing the sealed October observation archive avoids duplicating raw normalization; all hierarchy aggregates were recomputed after new eligibility checks.
- The full-month descriptive aggregate was not promoted into a predictive artifact.
- The November input-only overlap purge preserves independent train/incident separation for this analysis. It is not a claim of prospective knowledge at an October 31 deployment.
- Training retains the original quality-screened final-MTA-prediction labels. A stricter November evaluation recency guard does not retroactively change this training screen.
- Earlier October performance belongs to the original model. November results must be reported separately.
