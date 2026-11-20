# Experiment data

| File | Use |
|---|---|
| [October model](artifacts/october-2026-profiles-full-train.json.gz) and [its manifest](artifacts/october-2026-profiles-full-train.manifest.json) | Time- and incident-conditioned ETA corrections fitted on October 1–31, 2026. The [training report](reports/full-october-fit.md) describes support and exclusions. |
| [Recorded November passages](artifacts/november-recorded-passages.json.gz) | Frozen recommendations, walking times, supplied route templates and indexed historical train calls. |
| [Station coordinates](manifests/november-feed-station-coordinates.json) and [quality policy](config/november-feed-outcome-quality.json) | Physical plausibility check on the selected train's endpoints. |
| [Daily weekday ETA errors](reports/november-weekday-peak-delays-daily.csv) and [pooled errors](reports/november-weekday-peak-delays-pooled.csv) | Separate descriptive study of five original Google-selected paths, for morning, midday and evening. Signed seconds equal reconstructed arrival minus raw MTA forecast. |

## Scope and reproduction

The [replay](../algo/scripts/evaluate_recorded_boarding.py) uses the bundled inputs. It reruns boarding, transfers, arrival checks and scoring for the original decisions. The new input bundle indexes historical stop calls on the original route templates. Its source hashes identify the frozen decision file, journal archives, receipt files and vehicle archives. To rebuild it from locally acquired files, run `python data/scripts/build_recorded_boarding_inputs.py`. The [previous experiment inputs](artifacts/november-two-corridor-replay.json.gz) supply the frozen advice and templates. Full feeds and downloaded provider material remain local.

Historical inputs came from [Subway Data NYC](https://subwaydata.nyc/). [October](manifests/october-acquisition.json) and [November](manifests/november-2026-acquisition.json) acquisition manifests identify the raw files. [The source schema](docs/october-schema.md) describes normalized snapshots and endpoint labels.

The fitted model is included for inference. A separate full refit from the locally prepared October observation archive and normalized October/November inputs can be run with `python data/scripts/build_full_october_profiles.py`. It verifies hashes against the [observation manifest](manifests/profiles.json) and writes to `data/processed/full-october-refit/`. The earlier preparation scripts and research work are recoverable from the local Git branch `archive/pre-experiment-cleanup-20261120`.

Run the data tests from the repository root with `PYTHONPATH=algo:. python -m unittest discover -s data/tests`.
