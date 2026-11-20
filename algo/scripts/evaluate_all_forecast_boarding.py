"""Regenerate the two-corridor November results from their archived feed evidence."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.experiment_evidence import ExperimentEvidence
from data.route_outcome_sanity import load_outcome_quality
from stayorswitch.forecast_boarding_replay import replay_side

REPORT = ROOT / "algo/reports/november-all-forecast-boarding.json"
CATEGORIES = ("gain", "tie", "loss")


def any_saving_category(row):
    stay, alternative = row["bounds"]
    if stay is None or alternative is None:
        return None
    # Both threshold tests are linear in the durations. Agreement at every
    # corner establishes the classification across their entire range.
    outcomes = set()
    for original in stay:
        for other in alternative:
            saved = original - other if row["action"] == "SWITCH" else other - original
            if saved > 0:
                outcomes.add("gain")
            elif 10 * saved >= -original:
                outcomes.add("tie")
            else:
                outcomes.add("loss")
    return outcomes.pop() if len(outcomes) == 1 else "ambiguous"


def result_table(rows):
    from statistics import mean, median

    lines = [
        "| Corridor | Advice | Issued | Classified | Faster | Tie | Slower | Faster rate | Mean minutes saved | Median minutes saved |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for corridor, name in [
        ("grandcentral_boroughhall", "Grand Central to Borough Hall"),
        ("courtsquare_timessquare", "Court Square to Times Square"),
    ]:
        for action in ("STAY", "SWITCH"):
            group = [
                r for r in rows if (r["corridor"], r["action"]) == (corridor, action)
            ]
            counts = Counter()
            low, high = [], []
            for r in group:
                category = any_saving_category(r)
                if category not in CATEGORIES:
                    continue
                counts[category] += 1
                stay, alt = r["bounds"]
                chosen, other = (stay, alt) if action == "STAY" else (alt, stay)
                low.append((other[0] - chosen[1]) / 60)
                high.append((other[1] - chosen[0]) / 60)
            n = len(low)

            def minutes(stat):
                if not n:
                    return "—"
                first, last = f"{stat(low):.2f}", f"{stat(high):.2f}"
                return first if first == last else f"{first} to {last}"

            values = [
                name,
                action,
                len(group),
                n,
                *[counts[k] for k in CATEGORIES],
                f"{100*counts['gain']/n:.1f}%" if n else "—",
                minutes(mean),
                minutes(median),
            ]
            lines.append("| " + " | ".join(map(str, values)) + " |")
    return lines


def write_any_saving_report(rows):

    lines = [
        "# November weekday Stay/Switch experiment",
        "",
        "The October 1–31, 2026 historical ETA model supplied the frozen recommendations. The evaluation uses the November 2–6, 9–13 and 16–18 weekday cohort for two corridors selected after reviewing earlier results. Each observation is a recommendation time. Multiple decisions can involve the same trains or incident. The two corridors originally had 635 checkpoints. The table covers the 595 with Stay or Switch advice and excludes 10 Monitor and 30 Undetermined decisions. The sample includes service-problem checkpoints beyond the onset and across severity levels.",
        "",
        "Both routes start at the same decision time and include walking, waiting and transfers. A passenger is assumed to board the earliest compatible train whose fresh MTA departure forecast is strictly later than platform readiness. The selected train needs a screened arrival from the journal or a bounded vehicle observation. These are reconstructed journeys.",
        "",
        "Each comparison follows the original recommendation. Any positive saving counts as a gain. Zero saving or a loss up to and including 10% of the original Stay duration is a tie. A larger loss counts as slower. Percentages and time summaries use classifiable cases. Positive minutes indicate savings.",
        "",
    ]
    lines.extend(result_table(rows))
    lines += [
        "",
        f"Of {len(rows)} issued recommendations, {sum(row['category'] in CATEGORIES for row in rows)} have a classifiable comparison. Unknown outcomes are excluded from each faster rate. Stay is compared with the supplied alternative. Switch is compared with the original Stay.",
        "",
        "The uncertainty intervals reflect archived timing bounds. The table describes these two selected corridors and does not estimate performance across the subway system or an incremental advantage over raw MTA.",
        "",
        "[Per-recommendation records and train traces](november-all-forecast-boarding.json) · [Frozen replay inputs](../../data/artifacts/november-two-corridor-replay.json.gz)",
    ]
    REPORT.with_name("november-all-forecast-boarding-any-saving.md").write_text(
        "\n".join(lines) + "\n"
    )


def main():
    evidence = ExperimentEvidence()
    screen = load_outcome_quality(ROOT)
    rows = []
    for case in evidence.cases:
        start = case["cutoff"]
        sides = [
            replay_side(evidence, evidence.positions, screen, evidence.routes[route], start)
            for route in (case["reference"], case["alternative"])
        ]
        row = {key: value for key, value in case.items() if key != "cutoff"}
        row.update(bounds=[side["bounds"] for side in sides], replay=sides)
        row["category"] = any_saving_category(row)
        rows.append(row)
    if len(rows) != 595 or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Unexpected November recommendation cohort.")
    REPORT.write_text(json.dumps(dict(decision_source_sha256=evidence.decision_source_sha256,
                                      cases=rows), indent=2) + "\n")
    write_any_saving_report(rows)


if __name__ == "__main__":
    main()
