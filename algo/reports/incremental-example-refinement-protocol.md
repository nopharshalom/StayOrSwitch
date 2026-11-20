# Departure-time illustrations from previously positive events

The user explicitly permits separate examples at different departure times
even when they use the same selected train pair. This supplement therefore
refines three previously positive event/corridor pairs: Grand Central to Borough
Hall with incidents 274016 (Freeman St signal problem) and 274022 (Jackson Av
EMS assistance), and Port Authority to NYU Tandon with incident 273900
(mechanical problem). Event selection uses known earlier outcomes and is
explicitly post hoc. These examples must not be pooled into the five-corridor
1,132-checkpoint or 94-event performance estimates.

Before new outcome scoring, fix every 30-second offset from the first applicable
problem receipt through 120 minutes, plus all previously frozen receipt
checkpoints in those events. The grid was changed from the initially discussed
one-minute spacing to 30 seconds before input freezing or new label scoring,
to cover short boarding windows. No further outcome-adaptive grid refinement
is allowed. This produces 729 planned event/departure checkpoints.

Only exactly previously approved contemporaneous line, direction, segment,
exposure-source and notice-version signatures qualify. Keep the original
Google Stay paths, all candidate itineraries, historical profiles, as-of
freshness, five-minute predicted Switch threshold and ±3-minute outcome-tie
boundary. Port Authority retains the same 120-second baseline A/C platform
access; no new walking variants are part of this refinement.

Preserve each parent study's complete input projection and effective feed
ownership. Require identical predictions at every previously confirmed
checkpoint from the chosen events. Freeze new input predictions and sources
before opening outcome labels. Compare the raw-MTA strict policy's exact
selected Stay journey against the historical-profile strict policy's exact
selected Switch journey. “Raw MTA Stay” refers to the project's rule applied
to unmodified feeds, not an official MTA routing recommendation.

Report all qualifying disagreements, including losses, ties and unknowns.
Then select five to ten meaningful illustrative departure examples if available;
physical train-pair repetition is permitted and labeled. Mark reuse of the same
underlying selected-feed captures as well. Different departure clocks do not
establish independent service events or new physical observations. Avoid
counting identical corridor/departure timestamps twice under different notices.

Endpoint-age, raw-label and earlier-known-catchable-Stay diagnostics qualify
the examples after scoring. They do not replace the frozen selected trains.
Historical labels remain final MTA prediction proxies plus assumed walks,
not passenger arrival observations. Fixed-train-only gains remain qualified.

Runner: `algo/scripts/refine_incremental_examples.py` with `--prepare-inputs`,
`--verify-only`, and default scoring phases. Every new artifact uses the
`incremental-example-refinement-` prefix; previous results remain byte-identical.
