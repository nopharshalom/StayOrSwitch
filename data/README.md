# Experiment data

| File | Use |
|---|---|
| [October model](artifacts/october-2026-profiles-full-train.json.gz) and [its manifest](artifacts/october-2026-profiles-full-train.manifest.json) | Time- and incident-conditioned ETA corrections fitted on October 1–31, 2026. The [training report](reports/full-october-fit.md) describes support and exclusions. |
| [November replay inputs](artifacts/november-two-corridor-replay.json.gz) | Frozen decisions, route templates, as-of feed frames consumed by the replay, selected-train endpoint records, and vehicle observations. |
| [Station coordinates](manifests/november-feed-station-coordinates.json) and [quality policy](config/november-feed-outcome-quality.json) | Physical plausibility check on the selected train's endpoints. |
| [Daily weekday ETA errors](reports/november-weekday-peak-delays-daily.csv) and [pooled errors](reports/november-weekday-peak-delays-pooled.csv) | Separate descriptive study of five original Google-selected paths, for morning, midday and evening. Signed seconds equal reconstructed arrival minus raw MTA forecast. |

## Scope and reproduction

The [replay](../algo/scripts/evaluate_all_forecast_boarding.py) uses the bundled inputs. It reruns boarding, transfers, arrival checks and scoring for the original decisions. The input bundle contains the queries used by this fixed cohort. Its source hashes identify the original decision file and route archive. Full feeds and downloaded provider material remain local.

Historical inputs came from [Subway Data NYC](https://subwaydata.nyc/). [October](manifests/october-acquisition.json) and [November](manifests/november-2026-acquisition.json) acquisition manifests identify the raw files. [The source schema](docs/october-schema.md) describes normalized snapshots and endpoint labels.

The fitted model is included for inference. A separate full refit from the locally prepared October observation archive and normalized October/November inputs can be run with `python data/scripts/build_full_october_profiles.py`. It verifies hashes against the [observation manifest](manifests/profiles.json) and writes to `data/processed/full-october-refit/`. The earlier preparation scripts and research work are recoverable from the local Git branch `archive/pre-experiment-cleanup-20261120`.

Run the data tests from the repository root with `PYTHONPATH=algo:. python -m unittest discover -s data/tests`.
