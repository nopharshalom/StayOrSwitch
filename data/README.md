# Data

This directory is reserved for dataset documentation, source manifests, and data organization used by StayOrSwitch.

Planned sources include:

- MTA static GTFS for the transit network and service schedules.
- OpenStreetMap for walking connections.
- Historical GTFS-Realtime archives for feature extraction, label construction, training, and replay.
- Current MTA feeds for real-time route evaluation.

For each dataset, record its source, service dates, timezone, version or retrieval time, coverage, and processing steps. Keep inferred arrival labels distinct from independently verified arrival observations.

No raw archives are included in this initial setup. Record large archive locations and checksums in manifests rather than copying them into Git by default.

See the [routing and prediction roadmap](../algo/README.md) for the six-step implementation plan.
