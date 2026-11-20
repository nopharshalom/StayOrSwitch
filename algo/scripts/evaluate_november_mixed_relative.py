"""Replay three short and two long Google corridors using relative journey thresholds."""
from collections import Counter
from datetime import datetime, timedelta
from itertools import chain
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]
import evaluate_november as base
from evaluate_november_repair import predict
from data.november_mixed_routes import (
    BASE,
    COHORTS,
    SOURCES,
    CONFIG,
    LOCAL,
    ZONE,
    PAIRS,
    daily_evidence,
)
from data.october.sources import read_labels, read_snapshots, sha256
from stayorswitch.feed_execution import execute_route
from stayorswitch.october_evaluation import latest_at_cutoffs
from stayorswitch.severe import decide

OUT = ROOT / "algo/local/november-mixed-relative"
REPORT = ROOT / "algo/reports/november-mixed-relative"


def recommendation(prediction, ref, fixed=False):
    route = next(r for r in prediction["routes"] if r["id"] == ref)
    seconds = route["total_duration_seconds"]
    decision = decide(
        prediction,
        ref,
        switch_margin_seconds=300 if fixed else (seconds or 0) * 0.10,
        require_severe=False,
    )["strict_decision"]
    return dict(
        action=decision["action"],
        id=decision["recommended_itinerary_id"],
        stay_seconds=seconds,
        estimated_savings=decision["estimated_savings_seconds"],
        reason=decision["reason_codes"],
    )


def case_info(case, corridor, ref):
    return dict(
        id=corridor + "--" + case["id"].split("--", 1)[1],
        source_id=case["id"],
        corridor=corridor,
        cutoff=case["decision_at"],
        local_time=case["local_time"],
        family=case["incident_ids"][0],
        primary=case["primary"],
        severe=case["official_text_review"]["confirmed_impact"] == "SEVERE",
        header=case["exposure"][0]["notices"][0]["header"],
        ref=ref,
    )


def outcome(out):
    return dict(
        duration=out.get("total_duration_seconds")
        if out.get("status") == "INFERRED"
        else None,
        status=out.get("status"),
        reason=out.get("reason"),
        conditional=bool(out.get("conditional_on_unverified_selected_wait")),
    )


def choose(case, predictions):
    ref = case["ref"]
    case["model"] = recommendation(predictions["incident_profile"], ref)
    case["raw"] = recommendation(predictions["mta"], ref)
    case["fixed"] = recommendation(predictions["incident_profile"], ref, True)


def shorts(prior):
    cat = {c["id"]: c for c in prior["cases"] if c["corridor_id"] in COHORTS}
    source = ROOT / "algo/local/november-repair/frozen-forecast-cases.json.gz"
    assert (
        sha256(source)
        == "afde938f14092dd4b17b4e54322ae690f161f1c3863e717444756ad68eb1d259"
    )
    rows = {}
    for f in read_labels(source)["cases"]:
        if f["id"] not in cat:
            continue
        c = cat[f["id"]]
        row = case_info(c, c["corridor_id"], c["reference_route_id"])
        choose(row, f["predictions"])
        rows[row["id"]] = row
    artifact = prior["shared_route_execution"]
    assert sha256(ROOT / artifact["path"]) == artifact["sha256"]
    for case in read_labels(ROOT / artifact["path"])["cases"]:
        if case["case_id"] in rows:
            row = rows[case["case_id"]]
            row["outcomes"] = {k: outcome(v) for k, v in case["outcomes"].items()}
    return list(rows.values())


def needed_days(day, times):
    start = datetime.fromtimestamp(min(times) - 180, ZONE).date()
    end = datetime.fromtimestamp(max(times) + 7200, ZONE).date()
    return [
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    ]


def long_day(day, inputs, corridors, index, estimator, manifest, coords):
    cutoffs = sorted({c["decision_at"] for c in inputs})
    days = needed_days(day, cutoffs)
    paths = [LOCAL / (key + ".jsonl.gz") for key in days]
    alert_paths = [
        ROOT / "data/processed/november-2026" / (key + ".alerts.jsonl.gz")
        for key in days
    ]
    selected, _ = latest_at_cutoffs(
        chain.from_iterable(read_snapshots(path) for path in paths + alert_paths),
        cutoffs,
    )
    rows = []
    cache = {}
    for c in inputs:
        for corridor in corridors:
            key = corridor["id"]
            if SOURCES[key] != c["corridor_id"]:
                continue
            ref = corridor["reference_route_id"]
            at = c["decision_at"]
            row = case_info(c, key, ref)
            if (at, key) not in cache:
                cache[at, key] = {
                    mode: predict(
                        selected[at], corridor, at, index, estimator, mode, 120
                    )
                    for mode in ("mta", "incident_profile")
                }
            choose(row, cache[at, key])
            rows.append(row)
    del selected, cache
    # Outcomes are opened only after all advice for the date is fixed.
    templates = [r for co in corridors for r in co["routes"]]
    archive = daily_evidence(paths, day, manifest, manifest["days"], templates, coords)
    routes = {r["id"]: r for r in templates}
    results = {}
    for row in rows:
        ids = {row["ref"]} | {row[k]["id"] for k in ("raw", "model", "fixed")}
        row["outcomes"] = {}
        for rid in sorted(ids - {None}):
            q = (rid, row["cutoff"])
            if q not in results:
                results[q] = outcome(execute_route(routes[rid], archive, row["cutoff"]))
            row["outcomes"][rid] = results[q]
    return rows


def compare(row, left, right):
    if not left or not right:
        return "unknown"
    a = row["outcomes"].get(left, {}).get("duration")
    b = row["outcomes"].get(right, {}).get("duration")
    if a is None or b is None:
        return "unknown"
    gain = a - b
    return "gain" if gain > a * 0.10 else "loss" if gain < -a * 0.10 else "tie"


def stats(rows, mode="model"):
    actions = Counter(r[mode]["action"] for r in rows)
    counts = Counter(
        compare(r, r["ref"], r[mode]["id"])
        for r in rows
        if r[mode]["action"] == "SWITCH"
    )
    return [
        len(rows),
        actions["STAY"],
        actions["UNDETERMINED"] + actions["NOT_APPLICABLE"],
        actions["SWITCH"],
        *[counts[k] for k in ("gain", "tie", "loss", "unknown")],
    ]


def save_report(rows, prior, long_config):
    metadata = {
        "policy": {
            "forecast_margin": "at least 10% of same-policy predicted Stay duration",
            "outcome_tie": "within +/-10% inclusive of reconstructed Stay duration",
            "boarding_margin_seconds": 120,
            "long_cohort": "Matched to previously reviewed same-direction downstream F or A service problems",
        },
        "training": prior["training"],
        "source_report_sha256": sha256(BASE),
        "long_templates_sha256": sha256(CONFIG),
        "input_bindings": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (
                ROOT / "data/manifests/november-2026.json",
                ROOT / "data/manifests/november-2026-acquisition.json",
                ROOT / "algo/reports/november-feed-replay-selection-frozen.json",
                ROOT
                / "data/local/google-corridors/2026-11-20-current/official-stations.json",
                Path(__file__).resolve(),
                ROOT / "data/november_mixed_routes.py",
            )
        },
        "normalized_long_sources": {
            p.name: sha256(p) for p in sorted(LOCAL.glob("*.jsonl.gz"))
        },
    }
    rows.sort(key=lambda r: (r["cutoff"], r["id"]))
    assert len({r["id"] for r in rows}) == len(rows)
    narrow = [
        r
        for r in rows
        if r["raw"]["action"] == "STAY" and r["model"]["action"] == "SWITCH"
    ]
    groups = {
        "All weekdays": rows,
        "Earliest representatives": [r for r in rows if r["primary"]],
        "Qualified severe": [r for r in rows if r["severe"]],
        "November 16–18": [r for r in rows if r["local_time"][:10] >= "2026-11-16"],
        "Three short corridors": [r for r in rows if r["corridor"] in COHORTS],
        "Two long corridors": [r for r in rows if r["corridor"] in SOURCES],
    }
    per = {k: [r for r in rows if r["corridor"] == k] for k in (*COHORTS, *SOURCES)}
    groups.update(per)
    groups.update(
        {
            "Raw MTA Stay / model Switch": narrow,
            "Severe raw Stay / model Switch": [r for r in narrow if r["severe"]],
        }
    )
    groups["Primary raw Stay / model Switch"] = [r for r in narrow if r["primary"]]
    groups["Severe on long corridors"] = [
        r for r in groups["Two long corridors"] if r["severe"]
    ]
    summary = {k: stats(v) for k, v in groups.items()}
    training_groups = base.ProfileEstimator(base.PROFILE).groups
    trained_pairs = {
        (g["route_id"], g["from_stop_id"], g["to_stop_id"])
        for g in (json.loads(key) for key in training_groups)
    }
    long_pairs = {
        (leg["route_id"], leg["from_stop_id"], leg["to_stop_id"])
        for corridor in long_config
        for route in corridor["routes"]
        for leg in route["legs"]
    }
    matched_pairs = sorted(long_pairs & trained_pairs)
    assert len({r["local_time"][:10] for r in rows}) == 13
    assert set(per) == set(r["corridor"] for r in rows)
    assert len({(r["corridor"], r["family"]) for r in rows}) == len(
        groups["Earliest representatives"]
    )
    for r in rows:
        for mode in ("model", "raw"):
            d = r[mode]
            if d["action"] == "SWITCH":
                assert (
                    d["estimated_savings"] >= 0.10 * d["stay_seconds"]
                    and d["id"] != r["ref"]
                )
                assert d["id"] in r["outcomes"] and r["ref"] in r["outcomes"]
    by_reason = Counter()
    conditional = 0
    for r in rows:
        if r["model"]["action"] != "SWITCH":
            continue
        chosen = r["outcomes"][r["model"]["id"]]
        stay = r["outcomes"][r["ref"]]
        if chosen["duration"] is None:
            by_reason["Switch: " + str(chosen["reason"])] += 1
        elif stay["duration"] is None:
            by_reason["Stay: " + str(stay["reason"])] += 1
        else:
            conditional += bool(chosen["conditional"] or stay["conditional"])
    for count, stay, unsure, switch, g, t, l, u in summary.values():
        assert count == stay + unsure + switch and switch == g + t + l + u
    metrics = {
        "columns": [
            "checkpoints",
            "stay",
            "undetermined",
            "switch",
            "gain",
            "tie",
            "loss",
            "unknown",
        ],
        "groups": summary,
        "exact_training_pairs_for_new_legs": matched_pairs,
        "new_leg_count": len(long_pairs),
        "raw_policy_switch_vs_stay": stats(rows, "raw"),
        "undetermined_reason_per_long_corridor": {
            k: dict(
                Counter(
                    r["model"]["reason"][0]
                    for r in per[k]
                    if r["model"]["action"] == "UNDETERMINED"
                )
            )
            for k in SOURCES
        },
        "unknown_switch_reasons": dict(by_reason),
        "conditional_comparisons": conditional,
        "fixed_five_minute_recommendation_relative_scoring": stats(rows, "fixed"),
    }
    REPORT.with_suffix(".json").write_text(
        json.dumps(dict(metadata, metrics=metrics, cases=rows), indent=1) + "\n"
    )
    lines = [
        "# November weekday replay with relative thresholds",
        "",
        "Test dates: November 2–6, 9–13 and 16–18, 2026. Use the frozen October profile and a two-minute boarding margin. Recommend Switch at a predicted saving of at least 10% of that policy’s Stay duration. Score gains and losses strictly outside ±10% of the reconstructed Stay duration.",
        "",
        "| Scope | Cases | Stay | Undetermined | Switch | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k, v in summary.items():
        lines.append("| " + k + " | " + " | ".join(map(str, v)) + " |")
    lines += [
        "",
        "## Forecast margin sensitivity",
        "",
        "Keep the same ten-percent outcome threshold in both rows. Only the forecast threshold for issuing advice changes.",
        "",
        "| Scope and forecast threshold | Cases | Stay | Undetermined | Switch | Gain | Tie | Loss | Unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scope in ("All weekdays", "Three short corridors", "Two long corridors"):
        for key, threshold in (("fixed", "5 minutes"), ("model", "10%")):
            values = stats(groups[scope], key)
            lines.append(
                "| "
                + scope
                + ", "
                + threshold
                + " | "
                + " | ".join(map(str, values))
                + " |"
            )

    lines += [
        "",
        "The three short routes reuse frozen raw and corrected ETA predictions and feed-following outcomes. The long routes use archived Google paths and walks, original sampled train feeds, the same boarding-safe predictor and feed-following executor, screened journal endpoints and the same 300 km/h outcome sanity limit. The October profile uses its existing fallback groups when exact long segments lack training support.",
        "",
        "The event cohort is matched: Kew Gardens uses reviewed southbound F notices from the previously tested downstream F path; Inwood uses reviewed southbound A notices from the Port Authority path. New upstream-only incidents are outside this cohort. Inwood and Port Authority can share an incident. Each earliest representative is per corridor and notice family. The weekday samples and thresholds have prior exposure. MTA final predictions and fixed walks are duration proxies. Unknowns remain in denominators.",
        "",
        "Kew Gardens candidates include F, FX and E to R. Google also returned an E to A alternative with an unresolved transfer walk; this path is unavailable to the decision rule. Inwood includes A and 1 to 3. The strict decision rule may recommend a faster eligible alternative, but cannot assert Stay when a supplied alternative remains unassessed.",
        "",
        "For example, at 10:42:48 New York time on November 2 in Inwood, the model found seven A candidates, six 1 candidates and one 3 candidate after transfer readiness. The captured 1-line service context was UNKNOWN while the 3-line context was NORMAL. The strict decision could not assess the alternate even though train timing was available.",
        "",
        "With the earlier five-minute forecast threshold and the new 10% outcome band, the same cases give "
        + str(metrics["fixed_five_minute_recommendation_relative_scoring"])
        + " in the table column order.",
    ]
    lines += [
        "",
        f"Exact October training support covers {len(matched_pairs)} of {len(long_pairs)} new route/segment pairs.",
        f"{conditional} comparable Switch decisions depend on waiting until an updated feed despite a temporarily unverifiable intended departure.",
        "",
        "## Long-corridor examples",
        "",
    ]
    names = {r["id"]: r["name"] for c in long_config for r in c["routes"]}
    examples = []
    for key in SOURCES:
        for category in ("gain", "tie", "loss", "unknown"):
            sample = next(
                (
                    r
                    for r in per[key]
                    if r["model"]["action"] == "SWITCH"
                    and compare(r, r["ref"], r["model"]["id"]) == category
                ),
                None,
            )
            if sample:
                examples.append((sample, category))
    for r, category in examples:
        ref = r["ref"]
        rec = r["model"]["id"]

        def minutes(rid):
            val = r["outcomes"][rid]["duration"]
            return f"{val/60:.1f} min" if val is not None else "unknown"

        lines.append(
            f"- {r['local_time']} · {r['corridor']} · {names[ref]} ({minutes(ref)}) to {names[rec]} ({minutes(rec)}), {category}. "
            + " ".join(r["header"].split())
        )
    lines += [
        "",
        "## Reproduction",
        "",
        "Use the existing raw November archives, Google captures and frozen October profile. Run from the repository root:",
        "",
        "```sh",
        "PYTHONPATH=algo:. .venv/bin/python -m data.november_mixed_routes",
        ".venv/bin/python algo/scripts/evaluate_november_mixed_relative.py short",
        ".venv/bin/python algo/scripts/evaluate_november_mixed_relative.py long",
        ".venv/bin/python algo/scripts/evaluate_november_mixed_relative.py report",
        "```",
    ]
    REPORT.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps(metrics), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["short", "long", "report"])
    ap.add_argument("--dates", nargs="+", help="Process only these long-route dates.")
    ap.add_argument(
        "--wait-for-inputs",
        action="store_true",
        help="Wait for the active data preparation job.",
    )
    args = ap.parse_args()
    prior = json.loads(BASE.read_text())
    corridors = json.loads(CONFIG.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = [c for c in prior["cases"] if c["corridor_id"] in SOURCES.values()]
    days = sorted({c["local_time"][:10] for c in inputs})
    if args.stage == "short":
        (OUT / "short.json").write_text(json.dumps(shorts(prior)))
        return
    if args.stage == "report":
        rows = json.loads((OUT / "short.json").read_text())
        for day in days:
            rows.extend(json.loads((OUT / (day + ".json")).read_text()))
        save_report(rows, prior, corridors)
        return
    manifest = json.loads((ROOT / "data/manifests/november-2026.json").read_text())
    stations = json.loads(
        (
            ROOT
            / "data/local/google-corridors/2026-11-20-current/official-stations.json"
        ).read_text()
    )
    coords = {
        s["gtfs_stop_id"]
        + "S": dict(
            latitude=float(s["gtfs_latitude"]), longitude=float(s["gtfs_longitude"])
        )
        for s in stations
    }
    index = base.incident_index(base.source_days()[1])
    estimator = base.ProfileEstimator(base.PROFILE)
    for day in args.dates or days:
        if day not in days:
            raise ValueError("Date outside the weekday cohort: " + day)
        target = OUT / (day + ".json")
        if target.exists():
            continue
        selected = [c for c in inputs if c["local_time"][:10] == day]
        paths = [
            LOCAL / (d + ".jsonl.gz")
            for d in needed_days(day, [c["decision_at"] for c in selected])
        ]
        if not all(p.exists() for p in paths):
            if not args.wait_for_inputs:
                raise FileNotFoundError(
                    "Prepare the normalized data for " + day + " first."
                )
            print("Waiting for normalized inputs:", day, flush=True)
        while not all(p.exists() for p in paths):
            time.sleep(2)
        rows = long_day(day, selected, corridors, index, estimator, manifest, coords)
        staging = target.with_suffix(".part")
        staging.write_text(json.dumps(rows, sort_keys=True))
        staging.replace(target)
        print("Scored", day, len(rows), flush=True)


if __name__ == "__main__":
    main()
