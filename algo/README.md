# Stay/Switch algorithm

## Historical evaluation

Run `python algo/scripts/evaluate_all_forecast_boarding.py` from the repository root after installing the [project dependencies](requirements-live-lock.txt). It reconstructs both journeys for each of the 595 frozen recommendations and writes the [result table](reports/november-all-forecast-boarding-any-saving.md) and [case records](reports/november-all-forecast-boarding.json). The case field `bounds` contains Stay and alternative duration ranges in seconds, in that order. `category` scores the recommended action. Null bounds indicate missing evidence, and `ambiguous` means the range crosses an outcome threshold.

## App integration

1. Supply candidate itineraries, walking times, the user's current route and the MTA snapshots available at decision time. The [provider integration guide](docs/live-integration.md) covers Google and MTA inputs.
2. Run [the boarding-safe predictor](docs/boarding-safe-handoff.md) with `--mode all` to get raw MTA, time-profile and incident-profile forecasts for the same inputs.
3. Pass the forecast report to `python algo/scripts/run_commuter_advice.py FORECAST_REPORT.json`. Its `action` is `STAY`, `SWITCH`, `MONITOR` or `UNDETERMINED`. `reference` identifies the original itinerary and `route_id` identifies the recommendation when available. Inspect `basis` for the reason. The commuter policy uses a 10% predicted advantage threshold for Switch.

The [app contract](docs/contract.md) and [synthetic examples](examples/) cover UI states. Validate them with `python algo/scripts/validate_contract.py --self-test`. Run the algorithm tests with `PYTHONPATH=algo:. python -m unittest discover -s algo/tests`.
