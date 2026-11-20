# Current Google corridor capture and historical-path configuration

This experiment uses a current provider recommendation to choose each Stay
path. Its current duration is recorded for context; neither that duration nor
the current transit departure times are historical October outcomes.

The November 20 capture queried three corridors at approximately 10:54:47
America/New_York. Each response contained six raw candidates and one explicit
`DEFAULT_ROUTE`. The selected paths are F for Hayden LIC to NYU Tandon, 5 for
Grand Central to Borough Hall, and 7 for Court Square Park to Times Square.
The explicit default takes precedence over a slightly shorter alternative.

## Artifacts

- `data/manifests/google-corridors-2026-11-20.json` records capture hashes,
  timestamps, labels and all 18 raw route indices.
- `data/config/google-corridors-provider.json` contains ten accepted unique
  paths, station-mapping evidence and one explicit unavailable E-to-A candidate.
- `data/manifests/google-corridor-research-walks.json` records eight additional
  Google WALK requests needed to reconcile research candidates to the exact
  current origins and destinations.
- `data/config/google-corridors.json` combines 22 usable provider/research paths
  across the three corridors and preserves the unavailable provider candidate.

Provider payloads and intermediate normalized results remain under ignored
`data/local/google-corridors/2026-11-20-current/`. No credentials are written to
captures, manifests or route configuration. The official MTA station metadata
download is also retained locally, with its source URL and hash referenced by
the provider configuration.

## Route and walking rules

The Google Stay keeps its exact captured line and boarding/alighting sequence.
For Grand Central, default 5 and alternative 4 remain separate candidates;
the comparison should identify this as a same-station service substitution.
Repeated departures on the same provider path are deduplicated while all raw
indices and the original default duration remain available for inspection.

The provider's `routes.duration` does not necessarily equal the last transit
arrival plus egress walking minus the capture time. Both the raw duration and
the normalized clock-derived ETA/difference are retained. Do not relabel the
raw duration as an independently verified leave-now duration.

Usable provider walking steps are summed exactly around transit legs. A
research route reuses them only for the same origin/station or station/destination
pair. Other access and egress walks come from a new single-route Google WALK
query between the actual street endpoint and verified MTA station coordinates.
These coordinate queries do not independently establish platform-access time;
they are explicitly marked `PLATFORM_ACCESS_UNVERIFIED` and held fixed during
the historical replay. Existing research transfer assumptions retain
`authored_transfer_indices` for sensitivity analysis.

The captured pilot E-to-A route transfers at 14 Street but has no explicit
provider transfer-walk step. It remains unavailable with `MISSING_TRANSFER_WALK`;
no zero or invented walk is inserted. The research E-to-A and E-to-C routes via
Port Authority are separate, labeled research paths with authored transfers.

Station mapping checks the exact provider line, station name and coordinates
against the official MTA station catalog. The largest accepted station offset
is approximately 249.5 metres at Union Square R, close to the retained
250-metre mapping boundary. Historical train stop order still must be checked
at every replay cutoff; station metadata alone does not establish availability.

## Reproduction

The capture CLI deliberately refuses to overwrite existing provider captures,
preventing an accidental repeat of billable queries. A new current capture must
use a new output directory and undergo a new station/path review.

```sh
.venv/bin/python data/scripts/capture_google_corridors.py \
  --config data/config/google-corridors-2026-11-20.json \
  --output-dir data/local/google-corridors/2026-11-20-current \
  --manifest data/manifests/google-corridors-2026-11-20.json
```

With the saved November 20 responses and official station metadata, derive the
provider configuration and augment the research paths:

```sh
.venv/bin/python data/scripts/build_google_corridor_templates.py
.venv/bin/python data/scripts/augment_google_corridor_research_paths.py
```

The augmentation script reuses matching saved WALK responses, so repeating
that derivation does not issue further requests. Its station-pair mapping is
specific to this audited capture, not a general Google-to-MTA mapping service.
Never replace frozen experiment inputs simply because a later provider query
returns different alternatives.
