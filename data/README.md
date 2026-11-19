# Data

This directory is reserved for dataset documentation, source manifests, and data organization used by StayOrSwitch.

Planned sources include:

- Current itineraries and candidate alternatives supplied by Google Routes or another provider, including walking/transit legs and query timestamps.
- MTA static GTFS and station metadata as needed to match provider itineraries to MTA stops, directions, and services. We are not building a routing graph.
- Subway Data NYC raw GTFS-Realtime archives and accompanying CSVs for 2026-11-09 through 2026-11-15, inclusive, for feature extraction, labels, training, and evaluation.
- Current MTA train feeds and service information for live ETA estimation and comparison.
- Independently observed arrival samples for label validation and evaluation where available.

For each dataset, record its source, service dates, timezone, version or retrieval time, coverage, and processing steps. Keep inferred arrival labels distinct from independently verified arrival observations.

Use America/New_York service dates and preserve source and collection timestamps. Reserve whole dates for evaluation and prevent the same trip from appearing in multiple splits. Historical route-level replay needs date-appropriate service arrangements; current provider output is not a record of historical candidate routes.

Historical MTA snapshots do not include historical Google route ETAs. Keep provider predictions and MTA predictions separate when defining model targets and evaluating improvements.

No raw archives are included in this initial setup. Record large archive locations and checksums in manifests rather than copying them into Git by default.

See the [delay-aware ETA and Stay/Switch roadmap](../algo/README.md) for the seven-step development plan. The seven-day pilot archives have been selected but are not included by this documentation change.
