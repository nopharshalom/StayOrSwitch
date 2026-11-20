# November route-execution evidence

`data/route_archive.py` builds a separate, immutable source index for the
boarding-safe route replay. The existing November snapshots, labels, models
and earlier evaluation artifacts remain unchanged.

## Sources and scope

The builder reads the verified daily files named by
`data/manifests/november-2026.json`. It verifies their SHA256 hashes before use.
Inputs include the projected train snapshots and journal endpoint labels with
archived receipt confirmation. The source projection preserves all configured
endpoints, complete intervening stop sequences, identity conflicts and relevant
stop-status changes. It does not manufacture missing endpoints.

The train snapshots are the existing approximately one-minute archive sample,
not a new extraction of every raw capture. The execution method therefore
estimates travel among the observed services using screened final MTA
predictions. It is not an independent physical train or passenger measurement.
Snapshot coverage and path freshness have an explicit 120-second limit. All
original label quality flags remain active, including whole-trip schedule
change/rewrite exclusions. The November endpoint screen additionally requires
confirmation, matching identity and last observation within 180 seconds of
the inferred endpoint time.

## Evidence and uncertainty

Each indexed event retains its actual route, direction-specific boarding and
alighting stops, canonical train identity, normalized aliases, screened
departure/arrival values, quality flags and timestamped path observations.
Sequential aliases can share an event only through the established canonical
identity. Conflicting alias endpoints remain unusable. Simultaneous duplicate
identities are unknown observations; the builder never chooses the faster one.

Every path observation records when the next full snapshot supersedes it.
A compatible path that disappears from a subsequent snapshot cannot remain
valid solely because its generic freshness timer has not expired. Disappearance
does not establish arrival, departure or cancellation.

An explicit whole-trip `CANCELED` message can update an already observed
canonical train/path even when the cancellation message has an empty stop
list. It retains its capture/source timestamps and does not invent endpoints.
Explicit canceled or skipped-stop states are marked separately from omission;
simultaneous alias ambiguity cannot supply such terminal-state proof. The
executor determines whether a terminal state predates passenger readiness and
whether later evidence prevents resolving an earlier unknown candidate.

The executor supplies the same observation-window start for every leg:
decision cutoff minus 120 seconds. An unresolved candidate within that window
does not disappear from consideration merely because the passenger reaches a
later transfer platform. Unknown departure times remain potential ordering
blockers. A strict usable departure before platform readiness, or a strict
usable destination arrival before readiness, can exclude an already completed
segment. Other exclusions require the executor's explicit path rules.

Known future departures remain visible even when contemporaneous path evidence
is absent. They become uncertainty blockers rather than being silently removed
in favor of a later fully documented train. Future-only compatible observations
retain their real timestamps and cannot establish compatibility before boarding.
Unknown evidence older than the fixed observation window is outside the stated
observation scope; its exclusion is not proof of physical disappearance.

## API and persistence

`build_archive(root, manifest_path, templates, windows=..., cache_path=...,
manifest_output_path=...)` returns a `RouteArchive`. Windows cover each frozen
decision cutoff through its 7,200-second execution horizon; the builder includes
120 seconds of surrounding snapshot evidence. A callable `progress` argument
receives a message for each daily snapshot file being scanned.

The archive exposes:

- `events_for(leg, ready_at, end_at, observation_start_at=cutoff - 120)`;
- `coverage_for(feed_id, start, end, max_gap_seconds=120)`;
- `to_payload()` for reproducible persistence.

`load_archive(path)` reads the saved archive. The ignored compressed cache lives
under `data/processed/november-repair-v2/`. A small manifest under
`data/manifests/` records source hashes, code hashes, scope, counts and the cache
hash. A cache is reused only when its binding and content hash match. The route
executor and outcome comparisons live separately under `algo/`.
