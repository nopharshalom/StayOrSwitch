"""Evaluate commuter advice on the pinned mixed-corridor weekday cohort."""
import argparse
import json
import multiprocessing
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from itertools import chain

import evaluate_november_mixed_relative as previous
from data.october.sources import read_labels, read_snapshots, sha256
from stayorswitch.commuter_advice import commuter_advice

ROOT = previous.ROOT
PRIOR = previous.REPORT.with_suffix(".json")
OUT = ROOT / "algo/local/commuter-coverage"
REPORT = ROOT / "algo/reports/november-commuter-coverage"
CONTEXT = {}


def new_row(old, model, raw):
    decision = commuter_advice(model, raw, old["ref"])
    if decision["strict_action"] != old["model"]["action"]:
        raise ValueError("Previous recommendation failed to reproduce: " + old["id"])
    return {
        k: old[k]
        for k in (
            "id",
            "corridor",
            "ref",
            "local_time",
            "cutoff",
            "primary",
            "severe",
            "family",
        )
    } | {
        "before": old["model"]["action"],
        "before_route": old["model"]["id"],
        "decision": decision,
        "outcomes": dict(old["outcomes"]),
    }


def short(lookup):
    rows = []
    path = ROOT / "algo/local/november-repair/frozen-forecast-cases.json.gz"
    if (
        sha256(path)
        != "afde938f14092dd4b17b4e54322ae690f161f1c3863e717444756ad68eb1d259"
    ):
        raise ValueError("Frozen short forecasts changed")
    for item in read_labels(path)["cases"]:
        if item["id"] in lookup:
            p = item["predictions"]
            rows.append(new_row(lookup[item["id"]], p["incident_profile"], p["mta"]))
    return rows


def long_day(day):
    inputs = CONTEXT["days"][day]
    cutoffs = sorted({r["cutoff"] for r in inputs})
    days = previous.needed_days(day, cutoffs)
    paths = [previous.LOCAL / (d + ".jsonl.gz") for d in days]
    alerts = [
        ROOT / "data/processed/november-2026" / (d + ".alerts.jsonl.gz") for d in days
    ]
    snaps, _ = previous.latest_at_cutoffs(
        chain.from_iterable(read_snapshots(p) for p in paths + alerts), cutoffs
    )
    decisions = {}
    rows = []
    for old in inputs:
        k, at = old["corridor"], old["cutoff"]
        if (k, at) not in decisions:
            co = CONTEXT["corridors"][k]
            decisions[k, at] = [
                previous.predict(
                    snaps[at], co, at, CONTEXT["index"], CONTEXT["estimator"], mode, 120
                )
                for mode in ("incident_profile", "mta")
            ]
        rows.append(new_row(old, *decisions[k, at]))
    del snaps, decisions
    # Advice and its nominated comparator are now fixed for every time on this date.
    routes = {r["id"]: r for co in CONTEXT["corridors"].values() for r in co["routes"]}
    missing = defaultdict(list)
    for row in rows:
        d = row["decision"]
        if d["action"] in {"SWITCH", "STAY"}:
            rid = d["route_id"] if d["action"] == "SWITCH" else d["alternative_id"]
            if rid and rid not in row["outcomes"]:
                missing[rid, row["cutoff"]].append(row)
    if missing:
        m = CONTEXT["manifest"]
        archive = previous.daily_evidence(
            paths, day, m, m["days"], list(routes.values()), CONTEXT["coordinates"]
        )
        for (rid, at), items in missing.items():
            result = previous.outcome(previous.execute_route(routes[rid], archive, at))
            for r in items:
                r["outcomes"][rid] = result
    print(day, len(rows), "additional route reconstructions", len(missing), flush=True)
    return rows


def category(row):
    d = row["decision"]
    if d["action"] not in {"SWITCH", "STAY"}:
        return None
    other = d["route_id"] if d["action"] == "SWITCH" else d["alternative_id"]
    if not other:
        return "unknown"
    if row["ref"] not in row["outcomes"] or other not in row["outcomes"]:
        raise ValueError("Missing reconstruction for " + row["id"])
    return previous.compare(row, row["ref"], other)


def summary(rows):
    actions = Counter(r["decision"]["action"] for r in rows)
    return dict(
        cases=len(rows),
        old_undetermined=sum(r["before"] == "UNDETERMINED" for r in rows),
        compared=actions["STAY"] + actions["SWITCH"],
        actions=dict(actions),
        basis=dict(Counter(r["decision"]["basis"] for r in rows)),
        switch=dict(
            Counter(category(r) for r in rows if r["decision"]["action"] == "SWITCH")
        ),
        added_switch=dict(
            Counter(
                category(r)
                for r in rows
                if r["before"] == "UNDETERMINED" and r["decision"]["action"] == "SWITCH"
            )
        ),
        added_stay_alternative_vs_stay=dict(
            Counter(
                category(r)
                for r in rows
                if r["before"] == "UNDETERMINED" and r["decision"]["action"] == "STAY"
            )
        ),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["short", "long", "report"])
    args = p.parse_args()
    if sha256(PRIOR) != "31df3575f8caf15a4b0b9d7696fa0b6856cb42586ac39e855ef2218696820c29":
        raise ValueError("The baseline replay has changed.")
    old = json.loads(PRIOR.read_text())
    rows = old["cases"]
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "short":
        data = short({r["id"]: r for r in rows if r["corridor"] in previous.COHORTS})
        (OUT / "short.json").write_text(json.dumps(data))
        return
    if args.stage == "long":
        days = defaultdict(list)
        for r in rows:
            if r["corridor"] in previous.SOURCES:
                days[r["local_time"][:10]].append(r)
        stations = json.loads(
            (
                ROOT
                / "data/local/google-corridors/2026-11-20-current/official-stations.json"
            ).read_text()
        )
        CONTEXT.update(
            days=days,
            manifest=json.loads(
                (ROOT / "data/manifests/november-2026.json").read_text()
            ),
            corridors={c["id"]: c for c in json.loads(previous.CONFIG.read_text())},
            coordinates={
                s["gtfs_stop_id"]
                + "S": {
                    "latitude": float(s["gtfs_latitude"]),
                    "longitude": float(s["gtfs_longitude"]),
                }
                for s in stations
            },
            estimator=previous.base.ProfileEstimator(previous.base.PROFILE),
            index=previous.base.incident_index(previous.base.source_days()[1]),
        )
        with ProcessPoolExecutor(
            max_workers=3, mp_context=multiprocessing.get_context("fork")
        ) as pool:
            for day, data in zip(sorted(days), pool.map(long_day, sorted(days))):
                (OUT / (day + ".json")).write_text(json.dumps(data))
        return
    dates = sorted({r["local_time"][:10] for r in rows})
    result = [
        r
        for key in ["short"] + dates
        for r in json.loads((OUT / (key + ".json")).read_text())
    ]
    assert len(rows) == len(result) == len(set(r["id"] for r in result)) and {
        r["id"] for r in rows
    } == {r["id"] for r in result}
    for r in result:
        if r["before"] in {"STAY", "SWITCH"}:
            assert (
                r["decision"]["action"] == r["before"]
                and r["decision"]["route_id"] == r["before_route"]
            )
    groups = {
        "All weekdays": result,
        "Earliest representatives": [r for r in result if r["primary"]],
        "Severe": [r for r in result if r["severe"]],
        "November 16–18": [r for r in result if r["local_time"][:10] >= "2026-11-16"],
    }
    groups.update(
        {
            k: [r for r in result if r["corridor"] == k]
            for k in [*previous.COHORTS, *previous.SOURCES]
        }
    )
    counts = {k: summary(v) for k, v in groups.items()}
    REPORT.with_suffix(".json").write_text(
        json.dumps(
            dict(prior_sha256=sha256(PRIOR), summary=counts, cases=result),
            separators=(",", ":"),
        )
    )
    print(json.dumps(counts), flush=True)
    lines = [
        "# November weekday commuter advice coverage",
        "",
        "The same 2,562 checkpoints, 13 weekdays, five corridors and 10% thresholds as the [previous replay](november-mixed-relative.md). All previously definite recommendations are reproduced. MONITOR means there is no supported change recommendation. It is counted separately from comparisons; both MONITOR and UNDETERMINED remain unresolved in the comparison coverage metric.",
        "",
        "| Scope | Cases | Previous unresolved | Compared Stay | Switch | Monitor | No Stay ETA | Switch gain / tie / loss / unknown |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for k, s in counts.items():
        a = s["actions"]
        out = s["switch"]
        lines.append(
            "| "
            + " | ".join(
                map(
                    str,
                    [
                        k,
                        s["cases"],
                        s["old_undetermined"],
                        *[
                            a.get(v, 0)
                            for v in ("STAY", "SWITCH", "MONITOR", "UNDETERMINED")
                        ],
                        "/".join(
                            str(out.get(x, 0))
                            for x in ("gain", "tie", "loss", "unknown")
                        ),
                    ],
                )
            )
            + " |"
        )
    total = counts["All weekdays"]
    lines += [
        "",
        "## Outcomes of newly issued advice",
        "",
        "| Recommendation | Alternative faster by >10% | Within ±10% | Alternative slower by >10% | Unknown |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in [
        ("Switch", "added_switch"),
        ("Stay", "added_stay_alternative_vs_stay"),
    ]:
        lines.append(
            "| "
            + " | ".join(
                [label]
                + [
                    str(total[key].get(x, 0))
                    for x in ("gain", "tie", "loss", "unknown")
                ]
            )
            + " |"
        )
    lines += [
        "",
        "The alternative for a new Stay is the fastest usable alternative in the decision-time forecast. A faster alternative in the Stay row is a missed opportunity.",
        "",
        "## Remaining unresolved comparisons",
        "",
        "| Reason | Cases |",
        "|---|---:|",
    ]
    for code in ("ONLY_STAY_TIMED", "SWITCH_NOT_CORROBORATED", "NO_USABLE_STAY_ETA"):
        lines.append(f"| {code} | {total['basis'].get(code, 0)} |")
    lines += [
        "",
        "The frozen October 1–31 model and the two-minute boarding margin are used throughout. Positive savings must reach 10% of the forecast Stay duration for a Switch. An outcome is a gain or loss only when it falls outside ±10% of the reconstructed Stay duration. Added Switch advice requires the incident-profile and raw-MTA forecasts to agree on the same route. Both forecasts use the same underlying feeds.",
        "",
        "Advice uses only information available at departure. Outcome durations use screened final MTA predictions and fixed walking assumptions. The long corridors use service problems on the previously reviewed common downstream segment. The November data had prior project exposure and checkpoints can repeat within one incident.",
        "",
        "To reproduce from the existing mixed-corridor replay inputs, run the short, long and report stages of `algo/scripts/evaluate_commuter_coverage.py` in that order.",
    ]
    REPORT.with_suffix(".md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
