# Input coverage for Google-selected corridor paths

The three-corridor experiment fixes Stay and alternative route structures from
current Google Routes responses, then evaluates their historical journeys using
October test-week inputs. Current Google durations are provenance, not historical
outcome labels. Some supplied paths need stops or an actual service absent from
the original research projection.

This separate supplement adds the following verified southbound pairs:

| Actual service | Boarding stop | Alighting stop |
|---|---|---|
| 6 | Grand Central (`631S`) | 14 St–Union Sq (`635S`) |
| R | 14 St–Union Sq (`R20S`) | Court St (`R28S`) |
| 7 / 7X | Grand Central (`723S`) | 5 Av (`724S`) |

It preserves the original route spans and the earlier pre-incident extension,
including the Grand Central-to-Times Square 7 span. The earlier BDFM supplement
already supplies F from Bryant Park (`D16S`) to Jay St–MetroTech (`A41S`).
Actual route 6 is added explicitly; this does not invent historical support for
it in the frozen model. Its predictions use the existing disclosed fallback
when no supported historical group exists.

## Reproduce and integrate

Run from the repository root:

```sh
.venv/bin/python data/scripts/prepare_google_corridor_inputs.py
```

The projection configuration is `data/config/google-corridor-projection.json`.
Existing raw October 24–31 archives are read directly, without copying them or
changing the earlier projection. October 24 supplies boundary observations;
the evaluation week remains October 25–31.

The completed manifest is `data/manifests/google-corridor-inputs.json`. Its daily
artifacts live under ignored `data/processed/google-corridor-inputs/`, with the
same snapshot/trip/receipt structure as the original preparation.

For each date, **replace** numbered and NQRW observations with this supplement.
Keep BDFM from `data/manifests/preincident-inputs.json`, and original ACE, G and
alert observations. Never append old and new versions of the same feed capture.
The supplemental alert file exists only to verify equality with the original;
it is not another observation source.

The completed preparation covers all eight dates and took 472.937 seconds.
The parity audit compared 23,053 train captures. It added 315,580 route-6 trip
observations across captures (not independent trains) and 236,268 additional
stop updates on already-retained trips. It reused 0.53 GiB of existing raw
archives without copying them. The manifest binds producer, configuration,
source and output hashes; 19 focused regression tests cover the supplement.

The parity audit checks raw capture identities, hashes, freshness metadata,
existing trip descriptors/statuses, original stop values/order and existing
vehicle evidence. Only route-6 trip/vehicle additions and additional stop
updates are allowed. Raw receipt coverage and alert captures remain unchanged.

## Separate outcome labels

The manifest's `labels` artifact contains only additional endpoint records:

- Route 6: `631S` and `635S`.
- Route R: `R20S` and `R28S`.
- Routes 7 / 7X: `724S`.

Original endpoint values cannot be overwritten, including when a duplicate value
is identical. New observed endpoints must be backed by the supplemental input
inventory. Identity collision checks, journal windows, receipt confirmation and
the existing quality-screened final-prediction rules remain in force.

The evaluator opens these outcomes only after input-only incident/checkpoint
selection and its review are frozen. Merge the additional labels with
`data.google_corridor_inputs.merge_label_additions`; retain existing original
and D16S labels alongside them. A missing or unusable endpoint remains unknown.

No training data, fitted profile, original source file or previously published
result is replaced. Labels remain screened final MTA prediction proxies rather
than independently observed passenger arrivals. New-route coverage does not
establish that the route or every selected connection was historically usable;
the same-cutoff matcher and later outcome checks still decide those questions.
