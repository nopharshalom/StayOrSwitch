# Two additional current Google corridors

The user authorized expanding the experiment to at most five total corridors.
The two additional origin/destination pairs were fixed before querying Google
or consulting their outcome labels:

1. West 42nd Street / Seventh Avenue → Brooklyn Borough Hall, 209 Joralemon Street.
2. West 42nd Street / Eighth Avenue → NYU Tandon, 6 MetroTech Center.

Selection used existing projected endpoint coverage and official notice inputs.
For context, the inventory contains 51 route-2, 31 route-3, 63 route-A and 24
route-C incident families first observed in the October 25–31 test week with
at least one DISRUPTION or SEVERE version. These broad counts precede direction,
segment, active-period and unplanned-problem qualification; they are not the
final evaluation denominator or evidence of successful switching.

Exactly these two additional transit ODs were queried. Both returned six raw
alternatives and one explicit `DEFAULT_ROUTE`, retained even if another path
appeared convenient for the historical experiment. No sixth corridor was queried.

| Corridor | Current default | Deduplicated alternatives | Raw default duration |
|---|---|---|---:|
| Times Square → Borough Hall | 2, Times Sq-42 St → Borough Hall | 3; A via Port Authority → Jay St; F via Bryant Park → Jay St | 23m02s |
| Port Authority → Tandon | A, Port Authority → Jay St | C; R via Times Square → Jay St | 22m24s |

All seven paths are provider-generated direct subway journeys. They retain
exact lines, rather than pooling compatible 2/3 or A/C service. Every raw
candidate index remains linked to its derived path, including repeated
departures. Current provider durations supply context only; the replay uses
historical decision-time predictions and historical outcome proxies.

## Port Authority access assumption

Google's A/C responses start immediately with a transit step and omit access
walking. The original normalization rejection `MISSING_ACCESS_WALK` is preserved
in the raw summary. A separate Google WALK query from the same street origin to
the verified A27 station coordinate explicitly returned **zero seconds**. This
is a provider result for colocated/snapped street and station coordinates; it
does not independently measure stairs or time to the platform.

Before input selection is frozen or outcome labels are consulted, both A and C
therefore receive the same **120-second authored platform-access allowance**
in addition to the provider's zero-second street walk. The config records the
two values separately. The 120 seconds are not attributed to Google and are
not an extra penalty for switching between services at the same platform.

The evaluation also predeclares coupled 0- and 240-second platform-access
variants, changing A and C together. These variants must be predicted and
frozen before scoring. The baseline, variants and their selected trains remain
separate rather than choosing whichever assumption yields a favorable result.

All other access and egress durations are sums of explicit provider walking
steps, held fixed during historical replay. The mapper checks captured station
names, service lines and coordinates against the existing official MTA station
catalog, with one explicit `Jay St - MetroTech` spelling alias for R29S.
Historical stopping order and catchability still require replay verification.

## Data and artifacts

- Query configuration: `data/config/incremental-extra-corridors-2026-11-20.json`.
- Capture manifest: `data/manifests/incremental-extra-corridors-2026-11-20.json`.
- Walking manifest: `data/manifests/incremental-extra-walks.json`.
- Evaluation configuration: `data/config/incremental-extra-corridors.json`.
- Provider payloads: ignored `data/local/google-corridors/2026-11-20-extra/`.
- Mapping code: `data/incremental_extra_corridors.py`.
- Derivation script: `data/scripts/build_incremental_extra_corridors.py`.

The A/C, 2/3 and F endpoints already exist in the previously audited sources.
Google's R alternative requires Times Square's R16S endpoint, added through the
separate `data/manifests/incremental-extra-inputs.json` projection. Source
replacement ownership is explicit: original ACE/G and alerts, corrected BDFM,
supplemental numbered, and the new R16-containing NQRW projection. Additional
R16 labels are merged without overwriting earlier labels. No training profile
or prior frozen experiment is changed.

The derivation reuses the saved WALK response and is deterministic. It does not
issue a new query when matching saved input exists:

```sh
.venv/bin/python data/scripts/build_incremental_extra_corridors.py
PYTHONPATH=algo:. .venv/bin/python -m unittest data.tests.test_incremental_extra_corridors
```

Eight focused tests cover exact defaults, raw-index deduplication, corridor cap,
station distances, explicit access provenance and refusal to silently repair
unrelated provider errors. Reproduction of the full evaluation additionally
requires the local archived inputs referenced in its source manifests.
