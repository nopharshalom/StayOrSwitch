# Stay/Switch teammate guide

**Final demo: use mock data only.** Bundle the synthetic JSON fixtures with the app and let the selected demo scenario determine which fixture to render. Keep Google Routes, MTA feeds and the Python model out of the demo execution path. The function calls below are for development and testing only.

## Wire the demo to mock data

Each fixture contains a sample request and a ready-to-display `response`. Read `response.decision.action` for the card, `recommended_itinerary_id` for the route, and `estimated_savings_seconds` for the time difference. A null saving means the comparison is unavailable.

| Demo scenario | Fixture | Expected UI |
|---|---|---|
| Switch | [01-switch.json](../examples/01-switch.json) | Show the alternative and **10 minutes saved** (600 seconds). |
| Stay | [02-stay.json](../examples/02-stay.json) | Keep the current route selected. |
| Incomplete comparison | [05-unmatched-alternative.json](../examples/05-unmatched-alternative.json) | Show that the recommendation is undetermined. |

## What the algorithm does

| Step | What happens |
|---|---|
| 1. Resolve the addresses | The backend passes the rider’s origin and destination as address strings to Google Routes. Google resolves them while computing directions. We use the returned step and station coordinates to connect walking segments and match subway stops. Building entrance coordinates can remain unknown. The pilot inputs were Hayden LIC Apartments and NYU Tandon at 6 MetroTech Center. |
| 2. Get candidate routes | The [Google client](../stayorswitch/provider_client.py) requests transit alternatives with a subway preference. [Normalization](../stayorswitch/google_routes.py) extracts walking and subway legs, groups duplicate routes and assigns stable itinerary IDs. Alternatives can use different nearby stations. The caller supplies the original itinerary ID as Stay. |
| 3. Learn historical ETA errors | The October 1–31, 2026 fit used 870,415 eligible observations from Subway Data NYC. For arrivals and departures, it learned the mean signed error between an earlier forecast and a screened final MTA estimate. It groups errors by line/segment, day type, time of day, forecast horizon and service conditions. Sparse groups fall back to broader statistics or raw MTA timing. [Training report](../../data/reports/full-october-fit.md) |
| 4. Estimate each journey | At a common decision time, match each subway leg to MTA trains serving its directional platforms. Estimate access walking, waiting, riding, transfers and egress. The boarding check uses a 120-second margin by default. A historical delay correction alone cannot make a tight train catchable. |
| 5. Decide whether to switch | Compare the supplied alternatives with the original route. Switch requires a predicted saving of at least 10% of Stay time. When service evidence is incomplete, an additional Switch needs support from both the corrected and raw forecasts. |
| 6. Evaluate the advice | Freeze each original recommendation and reconstruct both journeys afterward. The main November experiment scored 451 decisions across two corridors. Switching was faster in 70 of 113 Grand Central → Borough Hall cases and 14 of 18 Court Square → Times Square cases under forecast-based boarding. The recorded-departure check found Court Square’s result particularly sensitive to train choice. [Main results](../reports/november-all-forecast-boarding-any-saving.md) · [Recorded-departure comparison](../reports/november-recorded-boarding.md) |

## Call the model in a development test

From the repository root, install the dependencies and set the import path:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r algo/requirements-live-lock.txt
export PYTHONPATH=algo:.
```

The Python example below uses the pilot route configuration and locally prepared November 18 captures. It makes no network calls. The trained profile ships with the repository. The two daily capture files live in the ignored `data/processed/` directory. On a fresh checkout, run `python -m unittest algo.tests.test_boarding_safe_cli algo.tests.test_commuter_advice` to exercise the forecast and advice functions with synthetic inputs.

```python
import json
from datetime import datetime
from pathlib import Path

from algo.scripts.run_boarding_safe import (
    DEFAULT_PROFILE, append_unavailable, load_asof, training_cutoff, unavailable_templates,
)
from data.delay_profiles import IncidentIndex, ProfileEstimator
from stayorswitch.boarding_safe import predict_routes
from stayorswitch.commuter_advice import commuter_advice

config = json.loads(Path("data/config/october.json").read_text())
reference = "f_direct"  # Original itinerary selected for this test.
cutoff = datetime.fromisoformat("2026-11-18T08:00:00-05:00").timestamp()
day = Path("data/processed/november-2026")
snapshots, alerts = load_asof([
    day / "2026-11-18.snapshots.jsonl.gz",
    day / "2026-11-18.alerts.jsonl.gz",
], cutoff)
profiles = ProfileEstimator(DEFAULT_PROFILE)  # Can be loaded once per process.
if cutoff < training_cutoff(profiles):
    raise ValueError("Decision time precedes the training boundary.")

incidents = IncidentIndex(alerts, max_age_seconds=300)
unavailable = unavailable_templates(config)
forecasts = {}
for mode in ("incident_profile", "mta"):
    forecast = predict_routes(
        snapshots, config["routes"], cutoff, mode=mode,
        estimator=profiles, incident_index=incidents, boarding_margin_seconds=120,
    )
    append_unavailable(forecast, unavailable, mode)
    forecasts[mode] = forecast

advice = commuter_advice(forecasts["incident_profile"], forecasts["mta"], reference)
print(advice["action"], advice["route_id"], advice["basis"])
```

`commuter_advice` takes two forecasts for the **same cutoff and route IDs**, plus the Stay ID. The result is a Python dictionary. `STAY` and `SWITCH` identify a recommended route. `MONITOR` means keep monitoring and `UNDETERMINED` means there is insufficient timing evidence. Inspect `basis` for the reason. `stay_seconds` and `alternative_seconds` are predicted door-to-door durations. The demo fixtures above use the separate UI contract, with the action nested under `response.decision`.

### Testing with addresses of your choice

The live test entry point is `integrate_live(client, api_key, cache_dir, *, origin, destination, current_itinerary_id=None)`. The [live CLI](../scripts/run_live_integration.py) sets up the HTTP client and reads the local Google Routes key. For example, run:

```sh
python algo/scripts/run_live_integration.py \
  --origin "Hayden LIC Apartments, 43-25 Hunter Street, Long Island City, NY" \
  --destination "NYU Tandon School of Engineering, 6 MetroTech Center, Brooklyn, NY" \
  --json
```

This call returns normalized itineraries and MTA matches. To score a new provider itinerary in the Python example, the calling code must assemble a route template. Keep its itinerary ID, copy access/transfer/egress walking durations in seconds, and map each subway leg to a feed ID, line ID and directional boarding/alighting stop IDs. Use the matched candidate’s `boarding_stop_id` and `alighting_stop_id` when the direction is resolved. Retain unresolved alternatives in `unavailable_candidates`. Pass the selected Stay ID and normalized MTA snapshots from the same decision time into the forecast and advice calls above. See the [route template example](../../data/config/october.json), [live setup](live-integration.md) and [forecast input details](boarding-safe-handoff.md).
