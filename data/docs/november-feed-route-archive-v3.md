# Feed-following archive views

The new replay follows the information a passenger could see at each feed
capture. It does not require proof of the actual departure order of every
unselected train. This data adapter separates current candidate views from
final selected-train evidence; the executor under `algo/` defines the passenger
choice and boarding rules.

## Reused evidence

`data/feed_route_archive.py` reads the verified final version of
`data/processed/november-repair-v2/route-events.json.gz`, bound by
`data/manifests/november-route-archive-v2.json`. It verifies the archive hash,
recorded source map, original binding and counts before indexing it. The source
contains 74,015 full-feed captures, 48,369 train/segment events and 3,308,710
origin observations for the fixed November weekday experiment and its journey
boundaries. The original snapshots are sampled at approximately one minute.

The original archive already retains explicit cancellation messages without
stop lists, skipped endpoint states, current path compatibility, identity
ambiguity and strict screened endpoint evidence. No old source file, label,
producer or result is rewritten. The new adapter does not duplicate the large
cache or rescan/download the original daily raw archives.

## Candidate views

`FeedRouteArchive.frames_for(leg, ready_at, horizon_at)` yields the latest full
capture at or before platform readiness, then every later capture through the
horizon. Each frame includes its capture and source time, eligibility, hash,
current candidates and next capture time. An unusable or empty full capture
remains visible; the adapter does not replace it with an older good snapshot.
When no initial capture exists, it yields an explicit missing-frame record
rather than backdating a later feed.

Candidates contain only contemporaneous observation fields: the observed trip
ID, immutable canonical identity, route/stops, raw departure and arrival
forecasts, path state, reason codes and explicit cancellation/skip state. Only
the members of that exact full capture appear. Omission on the next full
capture removes a train from that frame, but does not itself establish physical
departure or cancellation.

The next-capture and membership-expiration timestamps support the offline event
clock. They are not train travel-time forecasts and must not rank candidates.
No final departure/arrival value, endpoint-quality flag, future alias list or
future path observation is present in a selection view. Changing any outcome
label or its quality leaves these views unchanged.

## Selected-train outcomes

After choosing an event from the current view,
`FeedRouteArchive.event_for(leg, event_key)` returns its separate screened
departure/arrival evidence, flags and exact identity. This accessor checks
route membership and requires one exact event. It does not fill missing labels
or choose a better-recorded replacement.

The default loader additionally applies the versioned geographic outcome
screen from `data/route_outcome_sanity.py`, configured in
`data/config/november-feed-outcome-quality.json`. Its portable station subset
contains all 22 approved endpoint coordinates, copied from the archived
official MTA station source with exact provenance. An otherwise usable
departure/arrival pair implying a straight-line average above 300 km/h receives
the alighting flag `IMPLAUSIBLE_LEG_TRAVEL_TIME`. This is a deliberately
permissive data-quality ceiling, not a claim about subway operating speed.
Missing station coordinates make an otherwise complete outcome explicitly
unavailable. Original timestamp values are retained alongside the distance,
duration, speed and rule evidence in `outcome_quality`.

This screen is applied only after event selection, identically for all routes
and comparison directions. It never changes candidate views or makes the
executor select a better-recorded alternative. The source cache and its original
endpoint flags remain unchanged; the selected event is copied before adding
the extra outcome flag. The constructor accepts an optional `quality_screen`
for synthetic tests, while `load_feed_archive` enables the declared quality
configuration by default and binds its configuration, station subset and
producer hashes into the new manifest.

The executor must keep a selected train with missing evidence distinct from an
unselected train with missing evidence. Later visible delays, cancellations or
reordering can change a choice according to the declared causal policy; future
endpoint quality or final destination arrival must not trigger that change.
Times remain screened final MTA prediction proxies, not independent passenger
measurements.

## Loading and provenance

```python
from data.feed_route_archive import load_feed_archive

archive = load_feed_archive(
    repository_root,
    manifest_output_path="data/manifests/november-feed-route-archive-v3.json",
    progress=print,
)
```

`build_feed_archive` is an alias of the same function. The optional output is a
small manifest binding the reused source archive, its manifest, the new adapter
and index counts. A different existing output binding is rejected rather than
silently overwritten. The index lives in memory and does not add another raw
data package to the repository.

Run focused checks with:

```sh
PYTHONPATH=algo:. .venv/bin/python -m unittest data.tests.test_feed_route_archive
PYTHONPATH=algo:. .venv/bin/python -m unittest data.tests.test_route_outcome_sanity
```
