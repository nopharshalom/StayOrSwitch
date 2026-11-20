#!/usr/bin/env python3
"""Extend the sealed same-run protocol to the already-declared Brooklyn paths."""

from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo"), str(ROOT / "algo/scripts")]

import evaluate_feed_revision as runner
from stayorswitch.preincident_replay import BROOKLYN_POLICY


POLICY = dict(deepcopy(runner.POLICY),
    schema_version="same-train-forecast-revision-brooklyn-v1",
    origin=BROOKLYN_POLICY["origin"], destination=BROOKLYN_POLICY["destination"],
    routes=deepcopy(BROOKLYN_POLICY["routes"]),
    route_family_policy=BROOKLYN_POLICY["route_family_policy"],
    extension_reason="PRIOR_COURT_SQUARE_COHORT_HAS_TWO_UNUSABLE_STAY_OUTCOMES; SEARCH_EXISTING_OD_FOR_COMPARABLE_CASES_WITHOUT_GAIN_FILTERING",
    expansion_is_post_hoc=True,
    walking_sensitivity_scope="ONE_ACCESS_OR_EGRESS_COMPONENT; TRANSFER_WALK_REMAINS_FIXED",
)

_provenance = runner.provenance
_choose_pair = runner.choose_pair
_score = runner.score


def provenance():
    value = _provenance()
    value["extension_producer"] = runner.artifact(Path(__file__))
    value["preserved_court_square_freeze"] = runner.artifact(runner.REPORTS / "feed-revision-selection-frozen.json")
    value["expansion_reason"] = POLICY["extension_reason"]
    return value


def choose_pair(before, after, policy=None):
    return _choose_pair(before, after, POLICY if policy is None else policy)


def score():
    _score()
    output = runner.path("-test.md")
    text = output.read_text().replace(
        "The three supplied paths are 7, E and F with the already-declared walking assumptions",
        "The four supplied paths are direct 4/5, 7 then 2/3, walk to Times Square then 2/3, and walk to Bryant Park then F to Jay Street and walk, with the already-declared walking assumptions")
    text = text.replace("At T0 all three candidates", "At T0 all four candidates")
    text = text.replace("## All input-selected representatives",
        "This is a separate OD expansion after the Court Square same-run cohort produced two unusable Stay outcomes. It retains all prior artifacts and uses identical selection thresholds and lags. This coverage-motivated extension is post-hoc; it is not a new untouched evaluation. Walking stress tests vary one access or egress component; transfer walks remain fixed.\n\n## All input-selected representatives")
    output.write_text(text)


if __name__ == "__main__":
    runner.POLICY = POLICY
    runner.PREFIX = "feed-revision-brooklyn"
    runner.LOCAL = ROOT / "algo/local/october-feed-revision-brooklyn"
    runner.provenance = provenance
    runner.choose_pair = choose_pair
    runner.score = score
    runner.main()
