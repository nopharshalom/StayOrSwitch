"""Refit the unchanged ETA hierarchy on all October dates, with new eligibility.

The sealed observation archive includes every October representative before
training eligibility filtering. Reusing it avoids re-normalizing the raw feeds;
the descriptive aggregate is never promoted or renamed as a predictive model.
November files opened here contain input-only trip and alert inventories.
"""

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import time

from data.delay_profiles.build import (
    ProfileDatabase, _boundary_inventory, _incident_spans, canonical_trip,
    dates_between, distinct_legs, fit_database, profile_document, snapshot_stream,
)
from data.delay_profiles.common import (
    digest, end_of_date, file_sha256, local_fields, read_json, write_json,
)
from data.delay_profiles.estimator import ProfileEstimator
from data.delay_profiles.incidents import IncidentIndex


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data/artifacts/october-2026-profiles-full-train.json.gz"
MANIFEST = ROOT / "data/artifacts/october-2026-profiles-full-train.manifest.json"
REPORT = ROOT / "data/reports/full-october-fit.json"
FROZEN = ROOT / "data/manifests/full-october-fit-frozen.json"


def verified_source(path, expected):
    actual = file_sha256(path)
    if actual != expected:
        raise ValueError("Source hash differs from its sealed provenance: " + str(path))
    return actual


def validate_configuration(config, original):
    expected = deepcopy(original)
    expected["splits"] = {"train": ["2026-10-01", "2026-10-31"]}
    actual = {key: value for key, value in config.items() if key != "full_month_fit"}
    if actual != expected:
        raise ValueError("The full fit must preserve the original component scope and settings.")
    policy = config.get("full_month_fit", {})
    if policy.get("boundary_inputs_use_outcomes") is not False:
        raise ValueError("November boundary inputs must not include outcomes.")
    if policy.get("boundary_input_dates") != ["2026-11-01", "2026-11-18"]:
        raise ValueError("The full fit requires the declared November input-only window.")


def remap_observation(row, config, original):
    """Change only split membership; preserve all forecast/label/quality values."""
    day = row["date"]
    if not config["start_date"] <= day <= config["end_date"]:
        raise ValueError("A non-October observation entered full-month fitting.")
    if local_fields(row["decision_at"], config)["date"] != day:
        raise ValueError("Observation calendar date differs from its decision time.")
    expected = next((key for key, bounds in original["splits"].items()
                     if bounds[0] <= day <= bounds[1]), None)
    if row.get("split") != expected:
        raise ValueError("Unexpected split in the sealed observation archive.")
    return dict(row, split="train")


class ReusedObservationDatabase(ProfileDatabase):
    """Stream already-deduplicated observations without another large SQL copy."""

    def __init__(self, path, observations, config, original):
        super().__init__(path)
        self.path = Path(path)
        self.observations = Path(observations)
        self.config = config
        self.original = original
        self.day_counts = Counter()
        self.old_split_counts = Counter()
        self.row_count = 0
        self.peak_bytes = 0
        self.started = time.monotonic()

    def note_size(self):
        self.peak_bytes = max(self.peak_bytes, sum(
            candidate.stat().st_size for candidate in
            (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm"))
            if candidate.exists()))

    def rows(self):
        previous = None
        with gzip.open(self.observations, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                order = (row["decision_at"], row["id"])
                if previous is not None and order <= previous:
                    raise ValueError("Reused observation sequence is not uniquely ordered.")
                previous = order
                self.day_counts[row["date"]] += 1
                self.old_split_counts[row["split"]] += 1
                self.row_count += 1
                yield remap_observation(row, self.config, self.original)
                if self.row_count % 10000 == 0:
                    self.commit()
                    self.note_size()
                if self.row_count % 100000 == 0:
                    print(json.dumps({"stage": "FULL_OCTOBER_FIT", "rows": self.row_count,
                                      "elapsed_seconds": round(time.monotonic() - self.started, 1),
                                      "working_peak_bytes": self.peak_bytes}), flush=True)


def input_inventory(october_dir, november_dir, config):
    """Resolve cross-window identities without opening any November label file."""
    days = list(dates_between(config["start_date"], config["end_date"]))
    boundary = list(dates_between(*config["full_month_fit"]["boundary_input_dates"]))
    locations = [(day, Path(october_dir)) for day in days]
    locations += [(day, Path(november_dir)) for day in boundary]
    spans, counts, hashes = {}, Counter(), {}
    for day, directory in locations:
        previous = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        first = end_of_date(previous, config["timezone"])
        last = end_of_date(day, config["timezone"]) - .001
        source_path = directory / (day + ".source.json")
        source = read_json(source_path)
        if source.get("date") != day or source.get("stage") != "NORMALIZED":
            raise ValueError("Input inventory requires completed daily normalization provenance.")
        hashes[str(source_path.relative_to(ROOT))] = file_sha256(source_path)
        for kind, suffix in (("trips", "trips.json.gz"), ("alerts", "alerts.jsonl.gz")):
            path = directory / (day + "." + suffix)
            name = str(path.relative_to(ROOT))
            declared = source["outputs"][kind]
            if declared["path"] != name:
                raise ValueError("Input inventory path differs from its daily normalization manifest.")
            hashes[name] = verified_source(path, declared["sha256"])
        for trip in read_json(directory / (day + ".trips.json.gz")).values():
            identity = canonical_trip(trip)
            if identity is None:
                counts["unresolved_trip_day_identities"] += 1
                continue
            old = spans.get(identity)
            spans[identity] = (first, last) if old is None else (min(old[0], first), max(old[1], last))
            counts["trip_day_memberships"] += 1

    def alert_snapshots():
        for day, directory in locations:
            for snapshot in snapshot_stream(directory / (day + ".alerts.jsonl.gz")):
                counts["input_alert_snapshots"] += 1
                yield snapshot

    index = IncidentIndex(alert_snapshots(), max_age_seconds=config["alerts_max_age_seconds"])
    incident_spans = _incident_spans(index, end_of_date(boundary[-1], config["timezone"]))
    return index, spans, incident_spans, dict(counts), hashes


def component_coverage(config, groups, corridor_configs):
    """Expose exact versus route-wide support without reading November outcomes."""
    configured = {(x["route_id"], x["from_stop_id"], x["to_stop_id"])
                  for x in distinct_legs(config)}
    exact_groups, route_groups = Counter(), Counter()
    for key, value in groups.items():
        identity = json.loads(key)
        if value["event_count"] < config["min_profile_events"]:
            continue
        if identity["state"] != "ANY":
            continue
        component = (identity["route_id"], identity["from_stop_id"], identity["to_stop_id"])
        if identity["from_stop_id"] == "ANY":
            route_groups[identity["route_id"]] += 1
        else:
            exact_groups[component] += 1
    records = []
    for path in corridor_configs:
        for corridor in read_json(path)["corridors"]:
            for route in corridor["routes"]:
                for leg in route["legs"]:
                    for route_id in leg.get("route_ids", [leg["route_id"]]):
                        component = (route_id, leg["from_stop_id"], leg["to_stop_id"])
                        records.append({"corridor_id": corridor["id"], "itinerary_id": route["id"],
                                        "route_id": route_id, "from_stop_id": component[1],
                                        "to_stop_id": component[2], "configured_exact_component": component in configured,
                                        "supported_exact_time_groups": exact_groups[component],
                                        "supported_route_time_groups": route_groups[route_id],
                                        "qualification": "Support remains query-horizon/day dependent; this is an inventory, not an inference guarantee."})
    return {"configured_component_count": len(configured), "path_leg_records": records}


def write_readable_report(path, report, manifest):
    counts = report["counts"]
    lines = ["# Full October training for November analysis", "",
             "The original October experimental model and all earlier results remain unchanged.", "",
             "| Item | New model |", "|---|---|",
             "| Training dates | October 1–31, 2026, America/New_York |",
             "| Outcome confirmation cutoff | Strictly before November 1, 00:00 EDT (04:00 UTC) |",
             "| Boundary inventory | November 1–18 inputs only; no November outcomes used for fitting |",
             f"| Representative observations | {counts['representative_observations']:,} |",
             f"| Eligible observations | {counts['eligible_observations']:,} |",
             f"| Aggregate groups | {counts['profile_groups']:,} |",
             f"| Supported rule-classified severe groups | {report['supported_severe_groups']} |",
             f"| Fitting elapsed seconds | {report['elapsed_seconds']} |", "",
             "Observations are not unique passengers or complete train trips. Each aggregate deduplicates physical endpoint events. "
             "Supported severe groups satisfy the existing event and incident thresholds; they are not evidence of successful Switch outcomes.", "",
             "## Eligibility exclusions", "",
             "| Reason | Representative observations |", "|---|---:|"]
    for name, number in sorted(counts.items()):
        if name not in {"representative_observations", "eligible_observations", "profile_groups"}:
            lines.append(f"| {name} | {number:,} |")
    records = report["five_corridor_component_coverage"]["path_leg_records"]
    missing = {}
    for item in records:
        if not item["configured_exact_component"]:
            key = (item["route_id"], item["from_stop_id"], item["to_stop_id"])
            missing[key] = item["supported_route_time_groups"]
    lines += ["", "## Components without direct training coverage", "",
              "The five-corridor experiment keeps all approved alternatives. The following exact components were not in the original training projection. "
              "A route-wide fallback can be used only when its particular query group has sufficient support; otherwise MTA remains unchanged.", "",
              "| Line | Segment | Supported route-wide time groups |", "|---|---|---:|"]
    for (route_id, start, end), number in sorted(missing.items()):
        lines.append(f"| {route_id} | {start} → {end} | {number} |")
    lines += ["", "## Provenance and interpretation", "",
              f"- Artifact: `{manifest['artifact']}`.",
              f"- Artifact SHA256: `{manifest['sha256']}`.",
              f"- Content seal: `{manifest['profile_seal']}`.",
              "- Reusing the sealed October observation archive avoids duplicating raw normalization; all hierarchy aggregates were recomputed after new eligibility checks.",
              "- The full-month descriptive aggregate was not promoted into a predictive artifact.",
              "- The November input-only overlap purge preserves independent train/incident separation for this analysis. It is not a claim of prospective knowledge at an October 31 deployment.",
              "- Training retains the original quality-screened final-MTA-prediction labels. A stricter November evaluation recency guard does not retroactively change this training screen.",
              "- Earlier October performance belongs to the original model. November results must be reported separately.", ""]
    path.write_text("\n".join(lines))


def build_full_october(config_path, november_dir):
    started = time.monotonic()
    config_path, november_dir = Path(config_path).resolve(), Path(november_dir).resolve()
    for destination in (ARTIFACT, MANIFEST, REPORT, REPORT.with_suffix(".md"), FROZEN):
        if destination.exists():
            raise ValueError("Refusing to overwrite a full-month fit: " + str(destination))
    original_path = ROOT / "data/config/october.json"
    original, config = read_json(original_path), read_json(config_path)
    validate_configuration(config, original)
    source_manifest_path = ROOT / config["full_month_fit"]["source_manifest"]
    source_manifest = read_json(source_manifest_path)
    if source_manifest.get("stage") != "PREPARED" or source_manifest.get("complete_month_inputs") is not True:
        raise ValueError("The observation archive must be a complete prepared October month.")
    verified_source(original_path, source_manifest["config_sha256"])
    observations = ROOT / config["full_month_fit"]["observation_source"]
    if str(observations.relative_to(ROOT)) != source_manifest["observations"]["path"]:
        raise ValueError("Observation archive differs from the declared prepared source.")
    verified_source(observations, source_manifest["observations"]["sha256"])
    source_hashes = dict(source_manifest["source_sha256"])
    source_hashes[str(observations.relative_to(ROOT))] = source_manifest["observations"]["sha256"]
    source_hashes[str(source_manifest_path.relative_to(ROOT))] = file_sha256(source_manifest_path)
    for name, expected in source_hashes.items():
        verified_source(ROOT / name, expected)
    protected_paths = [ROOT / "data/artifacts/october-2026-profiles-train.json.gz",
                       ROOT / "data/artifacts/october-2026-profiles-train.manifest.json",
                       ROOT / "data/artifacts/october-2026-profiles-month-descriptive.json.gz",
                       ROOT / "data/manifests/profiles-frozen.json",
                       ROOT / "data/reports/profiles.json",
                       ROOT / "data/reports/profiles.md"]
    protected = {str(path.relative_to(ROOT)): file_sha256(path) for path in protected_paths}
    code_paths = [Path(__file__), ROOT / "data/scripts/build_full_october_profiles.py"]
    code_paths += sorted((ROOT / "data/delay_profiles").glob("*.py"))
    code_paths += sorted((ROOT / "data/october").glob("*.py"))
    code_hashes = {str(path.relative_to(ROOT)): file_sha256(path) for path in code_paths}
    config_sha = file_sha256(config_path)
    corridor_paths = [ROOT / "data/config/google-corridors.json",
                      ROOT / "data/config/incremental-extra-corridors.json"]
    source_hashes.update({str(path.relative_to(ROOT)): file_sha256(path) for path in corridor_paths})
    index, trip_spans, incident_spans, inventory, input_hashes = input_inventory(
        ROOT / "data/processed/october", november_dir, config)
    source_hashes.update(input_hashes)
    boundary_families = _boundary_inventory(index, incident_spans, config)
    print(json.dumps({"stage": "FULL_OCTOBER_INPUT_INVENTORY", "counts": inventory,
                      "boundary_families": boundary_families}), flush=True)
    directory = ROOT / "data/processed/full-october-fit"
    directory.mkdir(parents=True, exist_ok=True)
    db_path = directory / "aggregation.sqlite"
    if db_path.exists():
        raise ValueError("Remove only the abandoned new-fit scratch database before restarting.")
    database = ReusedObservationDatabase(db_path, observations, config, original)
    try:
        groups, report = fit_database(database, config, "train", trip_spans, incident_spans)
        database.note_size()
        if sorted(database.day_counts) != list(dates_between("2026-10-01", "2026-10-31")):
            raise ValueError("The reused observation archive does not cover all October dates.")
        report.update(input_only_boundary_families=boundary_families,
                      representative_observations_by_day=dict(sorted(database.day_counts.items())),
                      original_split_observation_counts=dict(database.old_split_counts),
                      input_inventory=inventory, working_database_peak_bytes=database.peak_bytes)
    finally:
        database.close()

    report["five_corridor_component_coverage"] = component_coverage(config, groups, corridor_paths)
    report["supported_severe_groups"] = sum(
        json.loads(key)["state"] == "SEVERE" and value["event_count"] >= config["min_profile_events"]
        and value["incident_count"] >= config["min_severe_incidents"] for key, value in groups.items())
    profile = profile_document(config, groups, "train", source_hashes, code_hashes, report)
    profile.update(model_version="october-2026-full-training-v1",
                   full_october_training=True, complete_month_inputs=True,
                   training_cutoff_at="2026-11-01T00:00:00-04:00",
                   reused_observation_archive=source_manifest["observations"],
                   november_outcomes_used_for_fit=False,
                   original_experiment_preserved=protected)
    profile["seal"] = digest({key: value for key, value in profile.items() if key != "seal"})
    ProfileEstimator(profile)
    if file_sha256(config_path) != config_sha:
        raise ValueError("Configuration changed during fitting.")
    for collection in (source_hashes, protected, code_hashes):
        for name, expected in collection.items():
            verified_source(ROOT / name, expected)
    elapsed_seconds = round(time.monotonic() - started, 1)
    write_json(ARTIFACT, profile)
    ProfileEstimator(ARTIFACT)
    write_json(REPORT, dict(report, stage="FULL_MONTH_TRAINED", profile_seal=profile["seal"],
                            elapsed_seconds=elapsed_seconds,
                            training_dates=["2026-10-01", "2026-10-31"],
                            november_outcomes_used_for_fit=False))
    frozen = {"schema_version": "full-october-fit-freeze-v1", "stage": "FROZEN_BEFORE_NOVEMBER_OUTCOME_ANALYSIS",
              "training_dates": ["2026-10-01", "2026-10-31"], "profile_seal": profile["seal"],
              "artifact": {"path": str(ARTIFACT.relative_to(ROOT)), "sha256": file_sha256(ARTIFACT)},
              "config": {"path": str(config_path.relative_to(ROOT)), "sha256": config_sha},
              "code_sha256": code_hashes, "source_sha256": source_hashes,
              "original_experiment_preserved": protected, "november_outcomes_used_for_fit": False,
              "input_only_boundary_dates": config["full_month_fit"]["boundary_input_dates"],
              "report": {"path": str(REPORT.relative_to(ROOT)), "sha256": file_sha256(REPORT)}}
    write_json(FROZEN, frozen)
    manifest = {"artifact": str(ARTIFACT.relative_to(ROOT)), "bytes": ARTIFACT.stat().st_size,
                "sha256": file_sha256(ARTIFACT), "profile_seal": profile["seal"], "fit_split": "train",
                "training_dates": ["2026-10-01", "2026-10-31"], "timezone": config["timezone"],
                "training_freeze": str(FROZEN.relative_to(ROOT)), "raw_data_included": False,
                "november_outcomes_used_for_fit": False,
                "purpose": "Full-October predictive refit; distinct from the immutable October experiment."}
    write_json(MANIFEST, manifest)
    write_readable_report(REPORT.with_suffix(".md"), read_json(REPORT), manifest)
    for suffix in ("", "-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    print(json.dumps({"stage": "FULL_OCTOBER_FIT_FROZEN", "artifact": manifest,
                      "counts": report["counts"], "elapsed_seconds": elapsed_seconds}), flush=True)
    return manifest
