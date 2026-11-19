# Simulated Integration Examples

All examples are fictional integration fixtures. Pilot address labels refer to Hayden LIC and NYU Tandon, but stop names, line identifiers, routes, trip IDs, and timing estimates are simulated. Coordinates are deliberately null until real entrances and provider data are verified. These fixtures are not evidence of ETA accuracy or time savings.

Each JSON file is an envelope containing `description`, `synthetic`, `http_status`, `request`, and `response`. Send only the `request` object to the future API, and use only `response` as its simulated output. No API server is supplied in Step 1. The frontend can load these static files to develop display states now.

| Example | Scenario |
|---|---|
| [01-switch](01-switch.json) | Delay correction makes a supplied alternative faster |
| [02-stay](02-stay.json) | Current itinerary is faster |
| [03-tie](03-tie.json) | Exact tie retains the current itinerary |
| [04-no-alternatives](04-no-alternatives.json) | No alternative supplied; no Stay claim |
| [05-unmatched-alternative](05-unmatched-alternative.json) | One alternative cannot be matched |
| [06-stale-feed](06-stale-feed.json) | Stale train observations |
| [07-missing-feed](07-missing-feed.json) | Missing train observations |
| [08-infeasible-current](08-infeasible-current.json) | Current itinerary is infeasible; no invented finite savings |
| [09-infeasible-alternative](09-infeasible-alternative.json) | Confirmed infeasible alternative |
| [10-no-reference](10-no-reference.json) | Estimates without a selected current itinerary |
| [11-provider-fallback](11-provider-fallback.json) | Displayable provider estimate is ineligible for comparison |
| [12-partial-switch](12-partial-switch.json) | Faster assessed alternative with incomplete candidate coverage |
| [13-invalid-request](13-invalid-request.json) | HTTP 422 for a dangling current-route reference |
| [14-transfer-switch](14-transfer-switch.json) | Two subway legs with transfer walking and a second wait |

Use the [contract](../docs/contract.md) to interpret states. In particular, `UNDETERMINED` is not `STAY`, null is not zero, and `comparison_complete: false` does not imply every supplied alternative was ruled out.
