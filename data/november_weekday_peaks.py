"""Score only the preselected weekday view of the frozen November peak inputs."""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from data.delay_profiles.common import file_sha256, read_json, write_json
from data.november_outcomes import screen_labels
from data.november_peak_analysis import (
    ROOT, SOURCE, FREEZE, MODEL_FREEZE, POLICY, PERIODS, artifact,
    daily_label_artifact, dates_between, summarize_rows, verify, write_csv,
)
from data.october import read_labels
from stayorswitch.october_evaluation import outcome_for


SELECTION = ROOT / "data/manifests/november-weekday-peak-selection.json"
SCORING_FREEZE = ROOT / "data/manifests/november-weekday-peak-scoring-frozen.json"
REPORT = ROOT / "data/reports/november-weekday-peak-delays.json"
SCORED = ROOT / "data/processed/november-peak-analysis/scored-weekday-checkpoints.json.gz"


def weekday_dates():
    return [day.isoformat() for day in dates_between(*POLICY["dates"]) if day.weekday() < 5]


def select_weekday_rows(rows):
    """Calendar-only view; retain order, predictions and preselected representatives."""
    allowed = set(weekday_dates())
    return [row for row in rows if row["date"] in allowed]


def summarize_weekdays(rows, corridors):
    daily, pooled, duration = [], [], []
    for corridor in corridors:
        candidates = [row for row in rows if row["corridor_id"] == corridor["id"]]
        for period, _, _ in PERIODS:
            group = [row for row in candidates if row["period"] == period]
            base = {"corridor_id": corridor["id"], "period": period, "day_type": "WEEKDAY"}
            pooled.append(dict(base, **summarize_rows(group)))
            for day in weekday_dates():
                daily.append(dict(base, date=day,
                                  **summarize_rows([row for row in group if row["date"] == day])))
            for band in ("00_15_MIN", "15_30_MIN", "30_60_MIN", "OVER_60_MIN", "UNAVAILABLE"):
                duration.append(dict(base, duration_band=band,
                                     **summarize_rows([row for row in group if row["duration_band"] == band])))
    order = {corridor["id"]: i for i, corridor in enumerate(corridors)}
    period_order = {period: i for i, (period, _, _) in enumerate(PERIODS)}
    daily.sort(key=lambda row: (order[row["corridor_id"]], row["date"], period_order[row["period"]]))
    return {"daily": daily, "pooled": pooled, "duration_band": duration}


def verify_selection():
    selection = read_json(SELECTION)
    for key in ("user_reporting_policy", "base_input_freeze", "prepared_inputs", "producer"):
        item = selection[key]
        if artifact(ROOT / item["path"]) != item:
            raise ValueError("Weekday selection evidence changed: " + key)
    reporting = read_json(ROOT / selection["user_reporting_policy"]["path"])
    if selection["dates"] != weekday_dates() or reporting["analysis_dates"] != weekday_dates():
        raise ValueError("The reporting view must retain exactly the thirteen approved weekdays.")
    prepared = verify()
    rows = select_weekday_rows(prepared["rows"])
    if [row["id"] for row in rows] != selection["selected_case_ids"] or len(rows) != 2860:
        raise ValueError("Weekday membership changed after its input-only freeze.")
    return prepared, rows, reporting


def code_provenance():
    return {name: file_sha256(ROOT / name) for name in (
        "data/november_weekday_peaks.py", "data/scripts/analyze_november_weekday_peaks.py")}


def score():
    if REPORT.exists():
        raise ValueError("The completed weekday report already exists; preserve it.")
    model = read_json(MODEL_FREEZE)
    if (model.get("stage") != "FROZEN_BEFORE_NOVEMBER_OUTCOME_ANALYSIS"
            or model.get("training_dates") != ["2026-10-01", "2026-10-31"]):
        raise ValueError("The full-October model must be sealed before November outcome scoring.")
    item = model["artifact"]
    if file_sha256(ROOT / item["path"]) != item["sha256"]:
        raise ValueError("The full-October model artifact changed.")
    prepared, selected, reporting = verify_selection()
    source = read_json(SOURCE)
    label_items = {day: daily_label_artifact(source, day) for day in weekday_dates()}
    for item in label_items.values():
        if file_sha256(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("The weekday outcome source differs from its prepared hash.")
    binding = {"schema_version": "november-weekday-peak-score-freeze-v1",
        "stage": "FROZEN_BEFORE_OUTCOME_SCORING", "weekday_selection": artifact(SELECTION),
        "base_input_freeze": artifact(FREEZE), "producer_sha256": code_provenance(),
        "full_october_model_freeze": artifact(MODEL_FREEZE), "full_october_model": model["artifact"],
        "model_used_for_descriptive_raw_mta_errors": False,
        "source_manifest": artifact(SOURCE), "daily_label_artifacts": label_items,
        "analysis_dates": weekday_dates(), "scheduled_checkpoints": len(selected)}
    if SCORING_FREEZE.exists() and read_json(SCORING_FREEZE) != binding:
        raise ValueError("An earlier scoring freeze belongs to different code or inputs.")
    write_json(SCORING_FREEZE, binding)
    rows = deepcopy(selected)
    by_date = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    quality = {}
    for day, candidates in sorted(by_date.items()):
        item = label_items[day]
        labels, quality[day] = screen_labels(read_labels(ROOT / item["path"]), POLICY["max_endpoint_age_seconds"])
        for row in candidates:
            outcome = outcome_for(row["forecast"], labels, row["decision_at"])
            row["outcome"] = outcome
            row["eta_error_seconds"] = (outcome["total_duration_seconds"] - row["forecast"]["total_duration_seconds"]
                                        if outcome["status"] == "INFERRED" else None)
        print({"stage": "WEEKDAY_PEAK_SCORE_DAY", "date": day,
               "usable": sum(row["outcome"]["status"] == "INFERRED" for row in candidates)}, flush=True)
    verify_selection()
    if code_provenance() != binding["producer_sha256"] or artifact(MODEL_FREEZE) != binding["full_october_model_freeze"]:
        raise ValueError("Frozen code or model evidence changed during scoring.")
    groups = summarize_weekdays(rows, prepared["corridors"])
    if len(groups["daily"]) != 195 or len(groups["pooled"]) != 15:
        raise ValueError("The weekday report must contain 195 daily cells and 15 pooled cells.")
    write_json(SCORED, {"scoring_freeze": artifact(SCORING_FREEZE), "rows": rows,
                        "quality_screening": quality})
    result = {"schema_version": "november-weekday-peak-delays-v1", "analysis_dates": weekday_dates(),
        "day_type": "WEEKDAY", "reporting_policy": reporting, "base_peak_policy": POLICY,
        "weekday_selection": artifact(SELECTION), "scoring_freeze": artifact(SCORING_FREEZE),
        "scored_checkpoints": artifact(SCORED), "corridors": prepared["corridors"],
        "overall": summarize_rows(rows), "groups": groups, "quality_screening": quality,
        "interpretation": ["Only the thirteen approved weekdays contribute outcomes or reported means.",
            "The original all-date input cohort remains unchanged as audit evidence.",
            "Primary means weight the fixed 15-minute departure grid among usable paired outcomes.",
            "Positive mean averages max(error,0) over all usable outcomes; unknown is never zero.",
            "These exact selected-train final-MTA-prediction proxies are not independent passenger observations.",
            "The full-October model was already sealed, but raw-MTA descriptive errors do not use its corrections."]}
    write_json(REPORT, result)
    for key, values in groups.items():
        write_csv(ROOT / ("data/reports/november-weekday-peak-delays-" + key.replace("_", "-") + ".csv"), values)
    write_markdown(result)
    write_heatmap(result)
    print({"stage": "WEEKDAY_PEAK_COMPLETE", "checkpoints": len(rows), "daily_cells": 195,
           "usable": result["overall"]["usable_checkpoints"]}, flush=True)


def write_markdown(result):
    def minutes(value):
        return "unavailable" if value is None else "{:.2f}".format(value / 60)
    overall = result["overall"]
    lines = ["# November weekday peak ETA delays", "",
        "Primary analysis dates: **November 2–6, 9–13 and 16–18, 2026**, America/New_York. Only these 13 weekdays contribute outcomes and means. November 19 is boundary evidence only. October 1–31 model training remains unchanged.", "",
        "The same five Google-selected Stay paths are sampled every 15 minutes: morning 06:00–10:00, midday 11:00–14:00, evening 16:00–20:00, with end times excluded. There are **2,860 scheduled corridor checkpoints and 195 daily cells**. Midday is an analysis window, not an empirically established peak.", "",
        "{} / {} scheduled weekday checkpoints have a complete raw-MTA forecast; **{} / {} ({:.1%})** have usable paired proxy outcomes after confirmation, endpoint-age, identity and boarding checks. Missing or missed-boarding outcomes remain unknown and never become zero.".format(
            overall["forecast_available_checkpoints"], overall["scheduled_checkpoints"], overall["usable_checkpoints"], overall["scheduled_checkpoints"], overall["coverage_fraction"]), "",
        "Signed ETA error is inferred final destination arrival minus the raw MTA forecast. Positive-only mean averages max(error, 0) over all usable outcomes; it is not mean delay conditional on being late. The main mean weights scheduled departure times equally. Repeated trains are retained for this departure-time estimand and are not independent samples. The secondary event-balanced mean uses the earliest frozen checkpoint per physical train sequence, date, period and forecast-duration band.", "",
        "Google's November 20 choice supplies the fixed path and walking assumptions; its current travel minutes are not historical outcomes. All five Stay paths have one train leg, so fixed egress cancels from the paired error after checking boarding feasibility. These are exact selected-train, final-MTA-prediction proxies, not independently measured passenger trips or an adaptive policy taking whichever same-line train arrives first.", "",
        "## Average ETA error by weekday period", "",
        "All time values are minutes. Pooled means retain each corridor's observed forecast-duration mix.", "",
        "| Corridor | Period | Signed mean | Positive-only mean | Event-balanced signed mean | Usable / scheduled | Distinct usable trains |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for row in result["groups"]["pooled"]:
        lines.append("| {} | {} | {} | {} | {} | {} / {} | {} |".format(row["corridor_id"], row["period"],
            minutes(row["grid_weighted"]["mean_signed_seconds"]), minutes(row["grid_weighted"]["mean_positive_seconds"]),
            minutes(row["event_balanced"]["mean_signed_seconds"]), row["usable_checkpoints"], row["scheduled_checkpoints"],
            row["usable_distinct_physical_sequences"]))
    lines += ["", "## Fixed Stay paths", "", "| Corridor | Stay |", "|---|---|"]
    for corridor in result["corridors"]:
        lines.append("| {} | {} |".format(corridor["id"], corridor["reference"]["name"]))
    lines += ["", "## Daily results", "",
        "[Daily CSV](november-weekday-peak-delays-daily.csv) contains all 195 weekday cells with means, usable/scheduled counts, distinct trains and event-balanced values. [Pooled CSV](november-weekday-peak-delays-pooled.csv) has the 15 corridor/period summaries. [Duration strata](november-weekday-peak-delays-duration-band.csv) expose the prediction-distance mix.", "",
        "![Weekday daily positive ETA error](november-weekday-peak-delay.png)", "",
        "The heatmap shows mean positive error among usable fixed-grid journeys. Grey means unavailable, not zero. An asterisk marks fewer than five usable observations. Daily cells have at most 16 morning, 12 midday or 16 evening observations, so daily averages have limited support even when unmarked; exact counts remain in the CSV.", "",
        "The required endpoints retain original quality checks and must have archived confirmation, matching train/stop identity, and absolute last-observed-to-proxy distance at most 180 seconds. Missing endpoints and missed selected trains retain distinct outcome statuses.", "",
        "[Complete JSON and provenance](november-weekday-peak-delays.json) includes all summaries and quality counts. The original 3,960-row all-date input freeze is preserved; it contributes no weekend outcomes to this weekday report.", ""]
    (ROOT / "data/reports/november-weekday-peak-delays.md").write_text("\n".join(lines))


def write_heatmap(result, output_path=None):
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data/.cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    days = result["analysis_dates"]
    corridors = [c["id"] for c in result["corridors"]]
    labels = ["Hayden LIC → Tandon (F)", "Grand Central → Borough Hall (5)",
              "Court Sq → Times Sq (7)", "Times Sq → Borough Hall (2)", "Port Authority → Tandon (A)"]
    lookup = {(r["corridor_id"], r["date"], r["period"]): r for r in result["groups"]["daily"]}
    arrays = []
    for period, _, _ in PERIODS:
        arrays.append(np.array([[np.nan if lookup[c, d, period]["grid_weighted"]["mean_positive_seconds"] is None
                                 else lookup[c, d, period]["grid_weighted"]["mean_positive_seconds"] / 60
                                 for d in days] for c in corridors]))
    finite = [float(v) for array in arrays for v in array.ravel() if np.isfinite(v)]
    vmax = max(max(finite) if finite else 1, 1)
    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("#d7dce0")
    figure, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    for axis, array, (period, start, end) in zip(axes, arrays, PERIODS):
        image = axis.imshow(np.ma.masked_invalid(array), aspect="auto", vmin=0, vmax=vmax, cmap=cmap)
        axis.set_yticks(range(len(corridors)), labels=labels, fontsize=10)
        axis.set_title("{} {:02d}:00–{:02d}:00".format(period.replace("_", " ").title(), start, end), loc="left", fontsize=13)
        axis.set_xticks(np.arange(-.5, len(days), 1), minor=True)
        axis.set_yticks(np.arange(-.5, len(corridors), 1), minor=True)
        axis.grid(which="minor", color="white", linewidth=1)
        axis.tick_params(which="minor", bottom=False, left=False)
        for y in range(len(corridors)):
            for x in range(len(days)):
                value = array[y, x]
                count = lookup[corridors[y], days[x], period]["usable_checkpoints"]
                label = "—" if not np.isfinite(value) else "{:.1f}{}".format(value, "*" if count < 5 else "")
                axis.text(x, y, label, ha="center", va="center", fontsize=9,
                          color="white" if np.isfinite(value) and value > vmax * .6 else "#242a30")
    axes[-1].set_xticks(range(len(days)), labels=[d[5:] for d in days], fontsize=10)
    axes[-1].set_xlabel("November 2026 · Weekdays only · New York local date", labelpad=8)
    figure.suptitle("Weekday average positive ETA error by departure period", fontsize=17, x=.02, ha="left", y=.985)
    figure.text(.02, .946, "Five fixed Google Stay paths · 13 weekdays · screened final-MTA-prediction outcomes", fontsize=11)
    figure.subplots_adjust(left=.29, right=.91, top=.90, bottom=.12, hspace=.30)
    coloraxis = figure.add_axes([.935, .22, .015, .58])
    figure.colorbar(image, cax=coloraxis, label="Mean positive ETA error (minutes)")
    figure.text(.02, .054, "Positive error = max(final prediction proxy − raw MTA forecast, 0), averaged over usable outcomes. Grey = unavailable.", fontsize=9)
    figure.text(.02, .035, "* Fewer than 5 usable observations. Daily cells have at most 16 / 12 / 16 morning / midday / evening checkpoints; counts are in the CSV.", fontsize=9)
    figure.text(.02, .016, "Daily means have limited support. Repeated trains are not independent samples; these outcomes are not measured passenger trips.", fontsize=9)
    figure.savefig(output_path or ROOT / "data/reports/november-weekday-peak-delay.png", dpi=180, facecolor="white")
    plt.close(figure)
