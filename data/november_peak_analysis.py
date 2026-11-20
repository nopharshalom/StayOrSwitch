"""Fixed departure-grid descriptions of November corridor ETA residuals.

This module measures the uncorrected MTA prediction for each fixed Google Stay
path. It does not train a model, select profitable incidents, or add unrelated
endpoint means. Input preparation and outcome scoring are separate operations.
"""

from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import date, datetime, time, timedelta
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

from data.delay_profiles import IncidentIndex
from data.delay_profiles.common import digest, file_sha256, read_json, write_json
from data.november_outcomes import screen_labels
from data.october import read_labels, read_snapshots
from data.october.labels import canonical_event_trip_id
from stayorswitch.october_evaluation import latest_at_cutoffs, outcome_for, project_snapshot
from stayorswitch.severe import predict_routes


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "data/processed/november-peak-analysis"
SOURCE = ROOT / "data/manifests/november-2026.json"
INPUT_SOURCE = ROOT / "data/manifests/november-2026-inputs.json"
PREPARED = DIRECTORY / "prepared-inputs.json.gz"
FREEZE = ROOT / "data/manifests/november-peak-inputs-frozen.json"
MODEL_FREEZE = ROOT / "data/manifests/full-october-fit-frozen.json"
REPORT = ROOT / "data/reports/november-peak-delays.json"
CORRIDOR_CONFIGS = ("data/config/google-corridors.json",
                    "data/config/incremental-extra-corridors.json")
PERIODS = (("MORNING_PEAK", 6, 10), ("MIDDAY", 11, 14), ("EVENING_PEAK", 16, 20))
POLICY = {
    "schema_version": "november-peak-delays-v1",
    "dates": ["2026-11-01", "2026-11-18"],
    "following_boundary_evidence_date": "2026-11-19",
    "following_boundary_is_analysis_exposure": False,
    "timezone": "America/New_York",
    "grid_seconds": 900,
    "periods": [{"id": name, "start_hour": start, "end_hour": end} for name, start, end in PERIODS],
    "train_max_age_seconds": 180,
    "alerts_max_age_seconds": 300,
    "max_endpoint_age_seconds": 180,
    "requires_archived_endpoint_confirmation": True,
    "requires_exact_normalized_train_and_stop_identity": True,
    "reference_policy": "EXISTING_CURRENT_GOOGLE_STAY_PATH; RAW_MTA_SELECTED_EXACT_TRAIN",
    "primary_estimand": "UNIFORM_DEPARTURE_GRID_MEAN_OF_PROXY_DESTINATION_ARRIVAL_MINUS_RAW_MTA_FORECAST",
    "secondary_estimand": "EARLIEST_INPUT_CHECKPOINT_PER_PHYSICAL_SEQUENCE_DATE_PERIOD_DURATION_BAND",
    "duration_bands_seconds": [0, 900, 1800, 3600],
    "selection_reads_outcomes": False,
    "missing_outcomes_are_zero": False,
    "independent_passenger_measurements": False,
    "all_service_contexts_included": True,
}


def dates_between(first, last):
    current = date.fromisoformat(first)
    end = date.fromisoformat(last)
    while current <= end:
        yield current
        current += timedelta(days=1)


def scheduled_grid(first=POLICY["dates"][0], last=POLICY["dates"][1]):
    """Construct local clock slots directly, including the November DST date."""
    zone = ZoneInfo(POLICY["timezone"])
    result = []
    for day in dates_between(first, last):
        day_type = "SATURDAY" if day.weekday() == 5 else "SUNDAY" if day.weekday() == 6 else "WEEKDAY"
        for name, start, end in PERIODS:
            for minute in range(start * 60, end * 60, POLICY["grid_seconds"] // 60):
                local = datetime.combine(day, time(minute // 60, minute % 60), zone)
                result.append({"decision_at": local.timestamp(), "local_time": local.isoformat(),
                               "date": day.isoformat(), "day_type": day_type, "period": name})
    return result


def duration_band(seconds):
    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds) or seconds < 0):
        return "UNAVAILABLE"
    for upper, name in ((900, "00_15_MIN"), (1800, "15_30_MIN"), (3600, "30_60_MIN")):
        if seconds < upper:
            return name
    return "OVER_60_MIN"


def physical_sequence(route):
    """Use only contemporaneous descriptor metadata, excluding start-time jitter."""
    if not route.get("timing_eligible"):
        return None
    result = []
    for leg in route.get("selected_legs", []):
        identity = canonical_event_trip_id({"feed_id": leg.get("feed_id"),
            "start_date": leg.get("service_date"), "route_id": leg.get("route_id"),
            "trip_id": leg.get("raw_trip_id")})
        if identity is None or not leg.get("from_stop_id") or not leg.get("to_stop_id"):
            return None
        result.append([identity, leg["from_stop_id"], leg["to_stop_id"]])
    return result or None


def mark_representatives(rows):
    """Mark every row, retaining earliest input representative before labels."""
    seen = {}
    for row in sorted(rows, key=lambda r: (r["decision_at"], r["id"])):
        sequence = row.get("physical_sequence")
        row["physical_sequence_key"] = digest(sequence) if sequence else None
        row["event_representative"] = False
        row["representative_case_id"] = None
        if not sequence:
            continue
        key = (row["corridor_id"], row["date"], row["period"],
               row["duration_band"], row["physical_sequence_key"])
        row["representative_case_id"] = seen.setdefault(key, row["id"])
        row["event_representative"] = row["representative_case_id"] == row["id"]
    return rows


def stats(values):
    """Keep signed, positive-over-all and conditional-positive means distinct."""
    values = list(values)
    if not values:
        return {"n": 0, "mean_signed_seconds": None, "mean_positive_seconds": None,
                "mean_if_late_seconds": None, "median_signed_seconds": None,
                "p90_signed_seconds": None, "share_over_five_minutes": None}
    ordered = sorted(values)
    late = [v for v in values if v > 0]
    position = (len(ordered) - 1) * .9
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    p90 = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return {"n": len(values), "mean_signed_seconds": statistics.mean(values),
            "mean_positive_seconds": statistics.mean(max(v, 0) for v in values),
            "mean_if_late_seconds": statistics.mean(late) if late else None,
            "median_signed_seconds": statistics.median(values), "p90_signed_seconds": p90,
            "share_over_five_minutes": sum(v > 300 for v in values) / len(values)}


def summarize_rows(rows):
    usable = [r for r in rows if r.get("outcome", {}).get("status") == "INFERRED"]
    representatives = [r for r in rows if r.get("event_representative")]
    scored_representatives = [r for r in representatives if r.get("outcome", {}).get("status") == "INFERRED"]
    unique = {r["physical_sequence_key"] for r in rows if r.get("physical_sequence_key")}
    usable_unique = {r["physical_sequence_key"] for r in usable if r.get("physical_sequence_key")}
    return {
        "scheduled_checkpoints": len(rows),
        "forecast_available_checkpoints": sum(bool(r["forecast"].get("timing_eligible")) for r in rows),
        "usable_checkpoints": len(usable),
        "unknown_checkpoints": len(rows) - len(usable),
        "coverage_fraction": len(usable) / len(rows) if rows else None,
        "distinct_physical_sequences": len(unique),
        "usable_distinct_physical_sequences": len(usable_unique),
        "event_representatives": len(representatives),
        "usable_event_representatives": len(scored_representatives),
        "representative_coverage_fraction": len(scored_representatives) / len(representatives) if representatives else None,
        "observed_dates": len({r["date"] for r in usable}),
        "scheduled_dates": len({r["date"] for r in rows}),
        "grid_weighted": stats(r["eta_error_seconds"] for r in usable),
        "event_balanced": stats(r["eta_error_seconds"] for r in scored_representatives),
        "outcome_status_counts": dict(Counter(r.get("outcome", {}).get("status", "NOT_SCORED") for r in rows)),
        "unknown_reason_counts": dict(Counter(r.get("outcome", {}).get("reason", "UNKNOWN") for r in rows
                                             if r.get("outcome", {}).get("status") != "INFERRED")),
        "duration_band_counts": dict(Counter(r["duration_band"] for r in rows)),
        "usable_duration_band_counts": dict(Counter(r["duration_band"] for r in usable)),
    }


def load_corridors():
    corridors = []
    for name in CORRIDOR_CONFIGS:
        corridors.extend(read_json(ROOT / name)["corridors"])
    if len(corridors) != 5 or len({c["id"] for c in corridors}) != 5:
        raise ValueError("Exactly the five previously selected corridors are required.")
    for corridor in corridors:
        matches = [r for r in corridor["routes"] if r["id"] == corridor["reference_route_id"]]
        if len(matches) != 1:
            raise ValueError("The fixed Google Stay path must be unique.")
    return corridors


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path)}


def producers():
    names = ["data/november_peak_analysis.py", "data/november_outcomes.py",
             "data/scripts/analyze_november_peaks.py", "data/october/labels.py",
             "data/october/sources.py", "data/delay_profiles/common.py",
             "algo/stayorswitch/october_evaluation.py", "algo/stayorswitch/severe.py",
             "algo/stayorswitch/matching.py"]
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "data/delay_profiles").glob("*.py"))]
    return {name: file_sha256(ROOT / name) for name in sorted(set(names))}


def compact_forecast(route):
    value = deepcopy(route)
    value["rejected_reason_counts"] = dict(Counter(x.get("reason", "UNKNOWN") for x in value.pop("rejected", [])))
    return value


def prepare():
    if PREPARED.exists() or FREEZE.exists():
        raise ValueError("A frozen peak input cohort already exists; preserve it.")
    source = read_json(INPUT_SOURCE)
    if source.get("stage") not in ("INPUTS_PREPARED", "PREPARED"):
        raise ValueError("November decision inputs are not prepared.")
    days = {d["date"]: d for d in source["days"]}
    if not {d.isoformat() for d in dates_between(*POLICY["dates"])}.issubset(days):
        raise ValueError("All 18 requested November input dates are required before freezing.")
    corridors = load_corridors()
    references = [next(r for r in c["routes"] if r["id"] == c["reference_route_id"]) for c in corridors]
    inputs = {}
    code = producers()
    config_artifacts = [artifact(ROOT / name) for name in CORRIDOR_CONFIGS]

    def verified(item):
        path = ROOT / item["path"]
        if file_sha256(path) != item["sha256"]:
            raise ValueError("Changed source: " + item["path"])
        inputs[item["path"]] = item["sha256"]
        return path

    def alerts():
        for day in sorted(days):
            yield from read_snapshots(verified(days[day]["outputs"]["alerts"]))

    index = IncidentIndex(alerts(), max_age_seconds=POLICY["alerts_max_age_seconds"])
    grid = scheduled_grid()
    by_date = defaultdict(list)
    for row in grid:
        by_date[row["date"]].append(row)
    rows, carry = [], {}
    for day in sorted(set(days) | set(by_date)):
        requested = by_date.get(day, [])
        if day in days:
            records = read_snapshots(verified(days[day]["outputs"]["snapshots"]))
            selected, carry = latest_at_cutoffs((project_snapshot(s, references) for s in records),
                                                [r["decision_at"] for r in requested], carry)
        else:
            selected = {r["decision_at"]: [] for r in requested}
        for checkpoint in requested:
            cutoff = checkpoint["decision_at"]
            prediction = predict_routes(selected[cutoff], references, cutoff, mode="mta", incident_index=index,
                                        train_max_age_seconds=POLICY["train_max_age_seconds"],
                                        alerts_max_age_seconds=POLICY["alerts_max_age_seconds"])
            route_predictions = {r["id"]: r for r in prediction["routes"]}
            for corridor in corridors:
                forecast = compact_forecast(route_predictions[corridor["reference_route_id"]])
                row = dict(checkpoint, id=corridor["id"] + "--" + str(int(cutoff)),
                           corridor_id=corridor["id"], reference_route_id=corridor["reference_route_id"],
                           forecast=forecast, duration_band=duration_band(forecast.get("total_duration_seconds")),
                           physical_sequence=physical_sequence(forecast), source_day_available=day in days)
                rows.append(row)
        print({"stage": "PEAK_INPUT_DAY", "date": day, "scheduled_rows": len(requested) * len(corridors)}, flush=True)
    mark_representatives(rows)
    if producers() != code or [artifact(ROOT / name) for name in CORRIDOR_CONFIGS] != config_artifacts:
        raise ValueError("Code or corridor settings changed during preparation.")
    if len(rows) != 3960:
        raise ValueError("The predeclared departure grid must contain 3,960 corridor checkpoints.")
    prepared = {"policy": POLICY, "producer_sha256": code, "corridor_config_artifacts": config_artifacts,
                "source_manifest_at_preparation": artifact(INPUT_SOURCE), "source_sha256": inputs,
                "corridors": [{"id": c["id"], "origin": c["origin"], "destination": c["destination"],
                               "reference_route_id": c["reference_route_id"], "reference": r}
                              for c, r in zip(corridors, references)],
                "rows": rows, "selection_reads_outcome_labels": False}
    write_json(PREPARED, prepared)
    write_json(FREEZE, {"schema_version": "november-peak-input-freeze-v1", "policy": POLICY,
                       "prepared_inputs": artifact(PREPARED), "producer_sha256": code,
                       "source_manifest_at_preparation": artifact(INPUT_SOURCE),
                       "corridor_config_artifacts": config_artifacts, "source_sha256": inputs,
                       "scheduled_checkpoints": len(rows),
                       "event_representatives": sum(r["event_representative"] for r in rows),
                       "selection_reads_outcome_labels": False})
    print({"stage": "PEAK_INPUTS_FROZEN", "rows": len(rows), "freeze": str(FREEZE)}, flush=True)


def verify():
    frozen = read_json(FREEZE)
    if frozen["policy"] != POLICY or frozen["producer_sha256"] != producers():
        raise ValueError("Frozen peak policy or producer changed.")
    if frozen["prepared_inputs"] != artifact(PREPARED):
        raise ValueError("Frozen peak inputs changed.")
    if frozen["source_manifest_at_preparation"] != artifact(INPUT_SOURCE):
        raise ValueError("The stable input-only source manifest changed.")
    for name, expected in frozen["source_sha256"].items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("Frozen source changed: " + name)
    if frozen["corridor_config_artifacts"] != [artifact(ROOT / name) for name in CORRIDOR_CONFIGS]:
        raise ValueError("Frozen corridor configuration changed.")
    return read_json(PREPARED)


def csv_row(row):
    result = {k: v for k, v in row.items() if not isinstance(v, (dict, list))}
    for scope in ("grid_weighted", "event_balanced"):
        for name, value in row[scope].items():
            result[scope + "_" + name] = value
    return result


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [csv_row(row) for row in rows]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def report_groups(rows, corridors):
    daily, pooled, day_types, duration, service = [], [], [], [], []
    for corridor in corridors:
        candidates = [r for r in rows if r["corridor_id"] == corridor["id"]]
        for period, _, _ in PERIODS:
            group = [r for r in candidates if r["period"] == period]
            base = {"corridor_id": corridor["id"], "period": period}
            pooled.append(dict(base, **summarize_rows(group)))
            for day in dates_between(*POLICY["dates"]):
                subset = [r for r in group if r["date"] == day.isoformat()]
                daily.append(dict(base, date=day.isoformat(), day_type=subset[0]["day_type"], **summarize_rows(subset)))
            for day_type in ("WEEKDAY", "SATURDAY", "SUNDAY"):
                day_types.append(dict(base, day_type=day_type,
                                      **summarize_rows([r for r in group if r["day_type"] == day_type])))
            for band in ("00_15_MIN", "15_30_MIN", "30_60_MIN", "OVER_60_MIN", "UNAVAILABLE"):
                duration.append(dict(base, duration_band=band,
                                     **summarize_rows([r for r in group if r["duration_band"] == band])))
            for state in sorted({r["forecast"].get("context", {}).get("state", "UNKNOWN") for r in group}):
                service.append(dict(base, archive_classifier_context=state,
                                    **summarize_rows([r for r in group if r["forecast"].get("context", {}).get("state", "UNKNOWN") == state])))
    return {"daily": daily, "pooled": pooled, "day_type": day_types, "duration_band": duration,
            "archive_classifier_context": service}


def daily_label_artifact(source, day):
    """Resolve the actual source manifest's separate outcome-artifact mapping."""
    if source.get("stage") != "PREPARED":
        raise ValueError("November outcome labels are not completely prepared.")
    item = source.get("daily_labels", {}).get(day)
    if not item or not item.get("path") or not item.get("sha256"):
        raise ValueError("The prepared source omits daily outcome labels for " + day)
    return item


def score():
    if REPORT.exists():
        raise ValueError("The peak report already exists; preserve its completed analysis.")
    model_freeze = read_json(MODEL_FREEZE)
    if (model_freeze.get("stage") != "FROZEN_BEFORE_NOVEMBER_OUTCOME_ANALYSIS"
            or model_freeze.get("training_dates") != ["2026-10-01", "2026-10-31"]):
        raise ValueError("Seal the approved full-October model before November outcome analysis.")
    model_item = model_freeze["artifact"]
    if file_sha256(ROOT / model_item["path"]) != model_item["sha256"]:
        raise ValueError("The full-October model differs from its sealed artifact.")
    model_evidence = {"freeze": artifact(MODEL_FREEZE), "artifact": model_item,
                      "used_to_calculate_descriptive_peak_errors": False}
    prepared = verify()
    source = read_json(SOURCE)
    rows = deepcopy(prepared["rows"])
    by_date = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    label_sources, quality = {}, {}
    for day, candidates in sorted(by_date.items()):
        item = daily_label_artifact(source, day)
        path = ROOT / item["path"]
        if file_sha256(path) != item["sha256"]:
            raise ValueError("Outcome source changed: " + item["path"])
        label_sources[item["path"]] = item["sha256"]
        labels, quality[day] = screen_labels(read_labels(path), POLICY["max_endpoint_age_seconds"])
        for row in candidates:
            outcome = outcome_for(row["forecast"], labels, row["decision_at"])
            row["outcome"] = outcome
            row["eta_error_seconds"] = (outcome["total_duration_seconds"] - row["forecast"]["total_duration_seconds"]
                                        if outcome["status"] == "INFERRED" else None)
        print({"stage": "PEAK_SCORE_DAY", "date": day,
               "usable": sum(r["outcome"]["status"] == "INFERRED" for r in candidates)}, flush=True)
    verify()
    groups = report_groups(rows, prepared["corridors"])
    scored_path = DIRECTORY / "scored-checkpoints.json.gz"
    write_json(scored_path, {"input_freeze": artifact(FREEZE), "label_source_sha256": label_sources,
                             "full_october_model_already_sealed": model_evidence,
                             "rows": rows, "quality_screening": quality})
    result = {"policy": POLICY, "input_freeze": artifact(FREEZE), "source_manifest": artifact(SOURCE),
              "scored_checkpoints": artifact(scored_path), "label_source_sha256": label_sources,
              "full_october_model_already_sealed": model_evidence,
              "corridors": prepared["corridors"], "overall": summarize_rows(rows),
              "groups": groups, "quality_screening": quality,
              "interpretation": ["Observed final-MTA-prediction proxies, not independent passenger measurements.",
                "Uniform departure-grid averages condition on paired outcomes; unknown observations are not zero.",
                "Exact forecast-selected trains are scored without hindsight replacement by an earlier train.",
                "All five fixed Stay paths have one transit leg; fixed egress cancels in the residual.",
                "Event-balanced values use pre-outcome earliest representatives within date/period/duration band.",
                "Pooled means retain the observed mix of forecast durations; strata expose that mix.",
                "Archive classifier context strata are not independently text-qualified severe incident claims."]}
    write_json(REPORT, result)
    for key, values in groups.items():
        write_csv(ROOT / ("data/reports/november-peak-delays-" + key.replace("_", "-") + ".csv"), values)
    write_markdown(result)
    write_heatmap(result)
    print({"stage": "PEAK_COMPLETE", "daily_cells": len(groups["daily"]),
           "pooled_cells": len(groups["pooled"]), "usable": result["overall"]["usable_checkpoints"]}, flush=True)


def write_markdown(result):
    def minutes(value):
        return "unavailable" if value is None else "{:.2f}".format(value / 60)
    lines = ["# November daily peak ETA delays", "",
        "Dates: November 1–18, 2026, America/New_York. November 19 is boundary outcome evidence only and contributes no departure checkpoints or daily means. Morning 06:00–10:00, midday 11:00–14:00, evening 16:00–20:00; end times excluded. The midday window is an analysis period, not an empirically established peak.", "",
        "The fixed 15-minute grid contains 3,960 corridor checkpoints. The main mean weights scheduled departure times equally among those with usable outcomes. Repeated trains are retained for this departure-time estimand; they are not independent observations. The adjacent event-balanced value selects the earliest input checkpoint per physical train sequence, date, period and forecast-duration band, before reading outcomes.", "",
        "Signed ETA error = inferred final destination arrival minus the uncorrected MTA forecast destination arrival. Positive-only mean averages max(error, 0) over all usable observations; it is not the conditional mean when late. All values below are minutes. Missing, stale, unconfirmed and missed-boarding outcomes remain unknown and never become zero.", "",
        "Google's November 20 route choices and fixed walks define the Stay paths. Current Google minutes are not used as historical outcomes. These are exact selected-train proxy journeys; a passenger staying on a line might choose a different earlier train. All five Stay paths have one train leg, so fixed egress cancels from the residual after boarding feasibility is verified.", "",
        "Only screened endpoints with absolute last-observed-to-event age at most 180 seconds, archived confirmation, and exact train/stop identity qualify. Forecast-duration strata and weekday/Saturday/Sunday results are in the accompanying CSV/JSON files. Pooled means retain their observed duration mix. No model is trained by this descriptive analysis.", "",
        "## Pooled periods", "",
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
    lines += ["", "## Daily results and coverage", "",
        "[Daily CSV](november-peak-delays-daily.csv) contains all 270 corridor/date/period cells, including unavailable cells. It includes signed and positive means, usable/scheduled counts, distinct trains, and the secondary event-balanced results. [Day-type CSV](november-peak-delays-day-type.csv) separates weekdays, Saturdays and Sundays; [duration-band CSV](november-peak-delays-duration-band.csv) exposes the prediction-horizon mix.", "",
        "![Daily positive ETA delay](november-peak-delay.png)", "",
        "The heatmap shows mean positive error among usable fixed-grid journeys. Grey means no usable outcome; it is not zero delay. An asterisk marks fewer than five usable observations. Each daily cell has at most 16 morning, 12 midday or 16 evening checkpoints; these daily averages have limited support even when unmarked. Exact usable/scheduled counts are in the CSV.", "",
        "Full summaries, outcome reasons, quality-screen counts and provenance: [JSON](november-peak-delays.json). Expanded exact predictions and outcomes remain local at the path recorded in that report.", ""]
    (ROOT / "data/reports/november-peak-delays.md").write_text("\n".join(lines))


def write_heatmap(result, output_path=None):
    """Render the standalone daily descriptive chart, without hidden zero fills."""
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data/.cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    days = [d.isoformat() for d in dates_between(*POLICY["dates"])]
    corridors = [c["id"] for c in result["corridors"]]
    labels = ["Hayden LIC → Tandon (F)", "Grand Central → Borough Hall (5)",
              "Court Sq → Times Sq (7)", "Times Sq → Borough Hall (2)",
              "Port Authority → Tandon (A)"]
    lookup = {(r["corridor_id"], r["date"], r["period"]): r for r in result["groups"]["daily"]}
    arrays = []
    for period, _, _ in PERIODS:
        arrays.append(np.array([[np.nan if lookup[c, d, period]["grid_weighted"]["mean_positive_seconds"] is None
                                 else lookup[c, d, period]["grid_weighted"]["mean_positive_seconds"] / 60
                                 for d in days] for c in corridors]))
    finite = [float(v) for array in arrays for v in array.ravel() if np.isfinite(v)]
    vmax = max(finite) if finite else 1
    vmax = max(vmax, 1)
    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("#d7dce0")
    figure, axes = plt.subplots(3, 1, figsize=(16, 9), sharex=True)
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
                axis.text(x, y, label,
                          ha="center", va="center", fontsize=8,
                          color="white" if np.isfinite(value) and value > vmax * .6 else "#242a30")
    axes[-1].set_xticks(range(len(days)), labels=[d[5:] for d in days], fontsize=9)
    axes[-1].set_xlabel("November 2026 · New York local date", labelpad=8)
    figure.suptitle("Average positive ETA error by departure period", fontsize=18, x=.02, ha="left", y=.985)
    figure.text(.02, .946, "Five fixed Google Stay paths · 15-minute departure grid · screened final-MTA-prediction outcomes", fontsize=11)
    figure.subplots_adjust(left=.255, right=.91, top=.90, bottom=.12, hspace=.30)
    coloraxis = figure.add_axes([.935, .22, .015, .58])
    figure.colorbar(image, cax=coloraxis, label="Mean positive ETA error (minutes)")
    figure.text(.02, .054, "Positive error = max(final prediction proxy − raw MTA forecast, 0), averaged over usable outcomes. Grey = unavailable.", fontsize=10)
    figure.text(.02, .035, "* Fewer than 5 usable observations. Daily cells have at most 16 / 12 / 16 morning / midday / evening checkpoints; exact counts are in the CSV.", fontsize=10)
    figure.text(.02, .016, "Daily means have limited support. Repeated trains are not independent samples, and these proxy outcomes are not measured passenger trips.", fontsize=10)
    figure.savefig(output_path or ROOT / "data/reports/november-peak-delay.png", dpi=180, facecolor="white")
    plt.close(figure)
