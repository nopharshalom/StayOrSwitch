"""Replay the frozen November recommendations against recorded station passages."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/"algo")]

from algo.scripts.evaluate_all_forecast_boarding import CATEGORIES, any_saving_category, result_table
from data.recorded_passages import BUNDLE, load_json
from data.route_outcome_sanity import load_outcome_quality
from stayorswitch.recorded_boarding import DepartureIndex, replay_side

REPORT = ROOT/"algo/reports/november-recorded-boarding.json"


def matched_switch_summary(cases):
    from statistics import mean

    previous = load_json(ROOT/"algo/reports/november-all-forecast-boarding.json")["cases"]
    original = {r["id"]: r for r in previous}
    text = ["## Switch outcomes on the same checkpoints", "",
            "Each row includes only Switch recommendations that both replays could classify. Positive minutes mean switching saved time.", "",
            "| Corridor | Paired checkpoints | Faster before | Faster now | Previous mean minutes saved | Current mean minutes saved |",
            "|---|---:|---:|---:|---:|---:|"]
    for corridor, name in (("grandcentral_boroughhall","Grand Central to Borough Hall"),
                           ("courtsquare_timessquare","Court Square to Times Square")):
        current = [r for r in cases if r["corridor"] == corridor and r["action"] == "SWITCH"
                   and r["category"] in CATEGORIES and original[r["id"]]["category"] in CATEGORIES]
        prior = [original[r["id"]] for r in current]

        def average(group):
            ends = [mean((r["bounds"][0][i]-r["bounds"][1][1-i])/60 for r in group)
                    for i in (0,1)]
            low, high = (f"{value:.2f}" for value in ends)
            return low if low == high else f"{low} to {high}"

        counts = [sum(r["category"] == "gain" for r in group) for group in (prior,current)]
        text.append(f"| {name} | {len(current)} | {counts[0]} | {counts[1]} | {average(prior)} | {average(current)} |")
    return text


def main(report=REPORT):
    data = load_json(BUNDLE)
    index = DepartureIndex(data["trains"])
    screen = load_outcome_quality(ROOT)
    cases = []
    for case in data["cases"]:
        row = dict(case)
        sides = [replay_side(index,screen,data["routes"][row[k]],row["cutoff"])
                 for k in ("reference","alternative")]
        row.update(replay=sides,bounds=[side["bounds"] for side in sides])
        row["category"] = any_saving_category(row)
        cases.append(row)
    if len({r["id"] for r in cases}) != len(cases) or len(cases) != 595:
        raise ValueError("The published recommendation cohort has changed.")
    report.write_text(json.dumps(dict(policy="FIRST_RECORDED_DEPARTURE",
                                      decision_source_sha256=data["decision_source_sha256"],
                                      cases=cases),indent=2)+"\n")
    reasons = Counter()
    for row in cases:
        if row["category"] not in CATEGORIES:
            reasons[", ".join(sorted({s["reason"] for s in row["replay"] if "reason" in s}))
                    or "AMBIGUOUS_SAVING_CATEGORY"] += 1
    lines = [
        "# November weekday Stay/Switch experiment using recorded departures", "",
        "The October model's 595 recommendations, decision times, route options and walking durations are frozen. These observations come from November 2–6, 9–13 and 16–18, 2026. Repeated decisions can involve the same train or incident.", "",
        "Both options board the earliest recorded train on the supplied line, direction and platform, including a departure exactly at readiness. A transfer starts at the selected train’s recorded arrival plus the supplied transfer walk. The allowed service IDs come from each frozen route template. For example, the Court Square Stay uses local 7 service.", "",
        "The outcomes use final MTA journal timestamps screened for recency, passage confirmation and service changes, supplemented by bounded observations of stopped vehicles. For a passage without a reliable departure, the index screens possible order using its journal and observed-stop timestamps with a three-minute allowance on either end, bounded below by any verified arrival at that platform. This allowance can reduce coverage. An earlier unresolved passage, overlapping departures, an unconfirmed destination or an implausible journey leaves the comparison unknown. Missing arrival evidence never promotes the next train. Results describe reconstructed journeys among archived services; missing observations can conceal a train.", "",
        "Any positive saving from following the recommendation counts as faster. Ties include zero saving and losses up to 10% of the reconstructed Stay duration. Larger losses count as slower. Percentages and minutes use classifiable cases. Time ranges reflect vehicle observation intervals.", "",
        *result_table(cases), "",
        f"Classifiable comparisons: {len(cases)-sum(reasons.values())} of {len(cases)}. Unresolved comparisons: {sum(reasons.values())}.", "",
        *matched_switch_summary(cases), "",
        "## Unresolved comparisons", "", "| Reason on either side | Cases |","|---|---:|",
        *[f"| {k} | {n} |" for k,n in reasons.most_common()], "",
        "[Case records](november-recorded-boarding.json) · [Replay inputs](../../data/artifacts/november-recorded-passages.json.gz) · [Previous forecast-boarding comparison](november-all-forecast-boarding-any-saving.md)", "",
    ]
    report.with_suffix(".md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
