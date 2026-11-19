"""Read immutable experiment inputs and verify model provenance."""

import gzip
import hashlib
import json
import math
import importlib.metadata
import platform
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPLIT_DATES = {
    "train": ("2026-11-02", "2026-11-08"),
    "validation": ("2026-11-09", "2026-11-11"),
    "test": ("2026-11-12", "2026-11-15"),
}


def runtime_versions():
    return {"python": platform.python_version(),
            "catboost": importlib.metadata.version("catboost"),
            "numpy": importlib.metadata.version("numpy")}


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


def repository_path(relative, root=ROOT):
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("Artifact path must remain within the repository.")
    return path


def output_for(manifest, target, split):
    matches = [item for item in manifest["outputs"]
               if item["target"] == target and item["split"] == split]
    if len(matches) != 1:
        raise ValueError("Expected exactly one target/split training view.")
    return matches[0]


def verify_data_manifest(manifest, *, root=ROOT):
    """Check view provenance without opening held-out labels."""
    from data.modeling.features import CATEGORICAL_FEATURES, FEATURE_NAMES, FEATURE_VERSION
    if manifest.get("stage") != "PREPARED" or manifest.get("feature_version") != FEATURE_VERSION:
        raise ValueError("A prepared model-data manifest with matching feature version is required.")
    if (manifest.get("feature_names") != {key: list(value) for key, value in FEATURE_NAMES.items()}
            or manifest.get("categorical_features") != {key: list(value) for key, value in CATEGORICAL_FEATURES.items()}):
        raise ValueError("Data manifest feature order or categorical types differ from current code.")
    for name, expected in manifest["code_sha256"].items():
        if sha256(repository_path(name, root)) != expected:
            raise ValueError("Model views were produced by different processing code: " + name)
    for name in ("config", "source_manifest", "report"):
        item = manifest[name]
        if sha256(repository_path(item["path"], root)) != item["sha256"]:
            raise ValueError("Model-data provenance dependency changed: " + name)


def load_rows(manifest, target, split, *, allow_test=False, root=ROOT):
    """Training callers cannot open final-test labels through this interface."""
    if split == "test" and not allow_test:
        raise ValueError("Final-test access requires an independently frozen experiment.")
    if split not in SPLIT_DATES:
        raise ValueError("Unknown chronological split.")
    output = output_for(manifest, target, split)
    path = repository_path(output["path"], root)
    if sha256(path) != output["sha256"]:
        raise ValueError("Training-view checksum does not match its manifest.")
    from data.modeling.features import FEATURE_NAMES, FEATURE_VERSION
    rows = []
    example_ids = set()
    lower, upper = SPLIT_DATES[split]
    with gzip.open(path, "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("feature_version") != FEATURE_VERSION or set(row["features"]) != set(FEATURE_NAMES[target]):
                raise ValueError("Training view differs from the canonical feature version or allowlist.")
            if row.get("eligible") is not True:
                raise ValueError("An ineligible label reached the model training view.")
            if row["target"] != target or row["split"] != split:
                raise ValueError("Target or chronological split mismatch.")
            decision_date = row.get("decision_date", row.get("decision_local_date"))
            if not isinstance(decision_date, str) or not lower <= decision_date <= upper:
                raise ValueError("Decision date is outside its frozen chronological split.")
            if not lower <= row.get("service_date", "") <= upper:
                raise ValueError("Service date is outside its frozen chronological split.")
            if row["example_id"] in example_ids:
                raise ValueError("Duplicate example in model view.")
            example_ids.add(row["example_id"])
            for field in ("baseline_seconds", "label_seconds", "target_residual_seconds", "weight"):
                if isinstance(row[field], bool) or not isinstance(row[field], (int, float)) or not math.isfinite(row[field]):
                    raise ValueError("Non-finite model view value: " + field)
            if row["weight"] <= 0 or row["baseline_seconds"] < 0 or row["label_seconds"] < 0:
                raise ValueError("Invalid model weight or component duration.")
            if abs(row["label_seconds"] - row["baseline_seconds"] - row["target_residual_seconds"]) > 1e-6:
                raise ValueError("Residual target does not match component semantics.")
            rows.append(row)
    if len(rows) != output["rows"] or not rows:
        raise ValueError("Training view has an unexpected or empty row count.")
    return rows


def seal(payload):
    return {"payload": payload, "sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest()}


def verify_frozen(path, *, root=ROOT):
    frozen = read_json(path)
    payload = frozen["payload"]
    if frozen["sha256"] != hashlib.sha256(canonical_bytes(payload)).hexdigest():
        raise ValueError("Frozen experiment seal does not match its contents.")
    if payload.get("test_labels_opened") is not False:
        raise ValueError("Experiment was not frozen before final-test access.")
    for relative, expected in payload["hashes"].items():
        if sha256(repository_path(relative, root)) != expected:
            raise ValueError("Frozen experiment dependency changed: " + relative)
    return frozen
