"""Train on development dates, seal artifacts, then evaluate once on test dates."""

from datetime import datetime, timezone
import gc
from pathlib import Path

from .artifacts import (ROOT, load_rows, read_json, repository_path, seal,
                        sha256, verify_frozen, write_json, runtime_versions, verify_data_manifest)
from .metrics import evaluate_predictions
from .models import (feature_matrix, feature_names, fit_historical, fit_support,
                     predictions, historical_residual, final_seconds, supported)


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _log(event, **details):
    import json
    print(json.dumps({"at": _now(), "event": event, **details}, sort_keys=True), flush=True)


def _versions():
    return runtime_versions()


def _pool(rows, target, names):
    from catboost import Pool
    from data.modeling.features import CATEGORICAL_FEATURES
    return Pool(feature_matrix(rows, target, names),
                label=[row["target_residual_seconds"] for row in rows],
                weight=[row["weight"] for row in rows],
                cat_features=[name for name in names if name in CATEGORICAL_FEATURES[target]],
                feature_names=names)


def _rolling_pool(rows):
    """Research inputs are explicit metadata, never selected for deployment."""
    from catboost import Pool
    from data.modeling.features import CATEGORICAL_FEATURES, ROLLING_FEATURE_NAMES
    names = feature_names("arrival", "core")
    matrix = feature_matrix(rows, "arrival", names)
    for values, row in zip(matrix, rows):
        values.extend(float("nan") if row.get("rolling_features", {}).get(name) is None
                      else row["rolling_features"][name] for name in ROLLING_FEATURE_NAMES)
    names += list(ROLLING_FEATURE_NAMES)
    return Pool(matrix, label=[row["target_residual_seconds"] for row in rows],
                weight=[row["weight"] for row in rows], feature_names=names,
                cat_features=list(CATEGORICAL_FEATURES["arrival"])), names


def _disjoint(train, validation):
    if {row["trip_identity"] for row in train} & {row["trip_identity"] for row in validation}:
        raise ValueError("A service-qualified trip crosses chronological splits.")


def _code_paths(root):
    paths = list((root / "algo/stayorswitch/model_training").glob("*.py"))
    paths += list((root / "data/modeling").glob("*.py"))
    paths += [root / "algo/scripts/train_models.py", root / "algo/scripts/evaluate_models.py",
              root / "data/scripts/build_model_data.py", root / "algo/docs/model-protocol.md",
              root / "algo/requirements-model-lock.txt"]
    return sorted(paths)


def train(config_path, *, root=ROOT):
    from catboost import CatBoostRegressor
    from data.modeling.features import CATEGORICAL_FEATURES, FEATURE_VERSION
    root = Path(root).resolve()
    config_path = Path(config_path).resolve()
    config = read_json(config_path)
    manifest_path = repository_path(config["data_manifest"], root)
    manifest = read_json(manifest_path)
    verify_data_manifest(manifest, root=root)
    directory = repository_path(config["artifact_directory"], root)
    frozen_path = directory / "frozen.json"
    if frozen_path.exists():
        raise ValueError("This experiment is already frozen. Use a new version for a new development run.")
    if repository_path(config["test_report"], root).exists():
        raise ValueError("Final-test results already exist for this experiment version.")
    directory.mkdir(parents=True, exist_ok=True)
    started = _now()
    initial_code_hashes = {str(path.relative_to(root)): sha256(path) for path in _code_paths(root)}
    configuration_hash = sha256(config_path)
    input_hash = sha256(manifest_path)
    development_report = {"experiment_version": config["experiment_version"], "started_at": started,
                          "split": "validation", "test_labels_opened": False, "targets": {},
                          "evidence_class": config["evidence_class"], "versions": _versions(),
                          "known_limitations": config["known_limitations"]}
    target_artifacts = {}
    used_artifacts = []
    all_development_trips = set()
    for target in config["targets"]:
        _log("loading_development_views", target=target)
        training_rows = load_rows(manifest, target, "train", root=root)
        validation_rows = load_rows(manifest, target, "validation", root=root)
        _disjoint(training_rows, validation_rows)
        all_development_trips.update(row["trip_identity"] for row in training_rows + validation_rows)
        history = fit_historical(training_rows, config["min_historical_group_events"])
        support = fit_support(training_rows, config["min_support_events"])
        history_path = directory / (target + "-history.json")
        support_path = directory / (target + "-support.json")
        write_json(history_path, history)
        write_json(support_path, support)
        used_artifacts.extend([history_path, support_path])
        candidates = {}
        best = None
        for candidate in config["candidates"]:
            names = feature_names(target, candidate["feature_set"])
            _log("fitting_candidate", target=target, candidate=candidate["name"],
                 training_rows=len(training_rows), validation_rows=len(validation_rows))
            model = CatBoostRegressor(
                iterations=config["iterations"], depth=candidate["depth"],
                learning_rate=config["learning_rate"], l2_leaf_reg=config["l2_leaf_reg"],
                random_seed=config["random_seed"], thread_count=config["thread_count"],
                loss_function="RMSE", eval_metric="RMSE", allow_writing_files=False,
                verbose=False, task_type="CPU")
            train_pool = _pool(training_rows, target, names)
            validation_pool = _pool(validation_rows, target, names)
            model.fit(train_pool, eval_set=validation_pool, use_best_model=True,
                      early_stopping_rounds=config["early_stopping_rounds"])
            values, applied = predictions(model, history, support, validation_rows, target, names, config)
            metrics = evaluate_predictions(validation_rows, values, model_applied={"model": applied})
            score = metrics["overall"]["methods"]["model"]["rmse_seconds"]
            candidates[candidate["name"]] = {
                "configuration": candidate, "tree_count": model.tree_count_,
                "feature_names": names, "metrics": metrics,
                "feature_importance": dict(zip(names, map(float, model.get_feature_importance()))),
            }
            _log("candidate_validated", target=target, candidate=candidate["name"],
                 event_weighted_rmse_seconds=score, tree_count=model.tree_count_)
            if best is None or score < best[0]:
                model_path = directory / (target + ".cbm")
                model.save_model(str(model_path))
                best = (score, candidate, names, model.tree_count_)
            del train_pool, validation_pool, values, model
            gc.collect()
        score, selected, names, tree_count = best
        model_path = directory / (target + ".cbm")
        used_artifacts.append(model_path)
        target_artifacts[target] = {
            "candidate": selected, "feature_names": names,
            "categorical_features": [name for name in names if name in CATEGORICAL_FEATURES[target]],
            "tree_count": tree_count, "validation_event_weighted_rmse_seconds": score,
            "model_path": str(model_path.relative_to(root)),
            "history_path": str(history_path.relative_to(root)),
            "support_path": str(support_path.relative_to(root)),
            "training_rows": len(training_rows), "validation_rows": len(validation_rows),
        }
        rolling_report = {"status": "NOT_APPLICABLE", "eligible_for_selection": False}
        if target == config["rolling_research"]["target"]:
            if (config["rolling_research"]["eligible_for_selection"] or
                    config["rolling_research"]["evaluate_on_test"]):
                raise ValueError("Rolling research cannot select or test this deployment candidate.")
            _log("fitting_validation_only_rolling_research", target=target)
            research = CatBoostRegressor(
                iterations=config["iterations"], depth=config["rolling_research"]["depth"],
                learning_rate=config["learning_rate"], l2_leaf_reg=config["l2_leaf_reg"],
                random_seed=config["random_seed"], thread_count=config["thread_count"],
                loss_function="RMSE", eval_metric="RMSE", allow_writing_files=False, verbose=False)
            research_training, research_names = _rolling_pool(training_rows)
            research_validation, _ = _rolling_pool(validation_rows)
            research.fit(research_training, eval_set=research_validation, use_best_model=True,
                         early_stopping_rounds=config["early_stopping_rounds"])
            raw = research.predict(research_validation)
            mask = [supported(support, row, config["max_horizon_seconds"]) for row in validation_rows]
            research_values = {
                "mta": [row["baseline_seconds"] for row in validation_rows],
                "history": [final_seconds(row["baseline_seconds"], historical_residual(history, row)) for row in validation_rows],
                "research_model": [final_seconds(row["baseline_seconds"], float(delta) if allowed else 0.0)
                                   for row, delta, allowed in zip(validation_rows, raw, mask)],
            }
            rolling_report = {
                "status": "VALIDATION_ONLY_RESEARCH", "eligible_for_selection": False,
                "tested_on_final_test": False, "live_enabled": False,
                "reason": "Equivalent online rolling history, sampling and cold-start behavior do not yet exist.",
                "tree_count": research.tree_count_, "feature_names": research_names,
                "feature_importance": dict(zip(research_names, map(float, research.get_feature_importance()))),
                "metrics": evaluate_predictions(validation_rows, research_values, model_applied={"research_model": mask}),
            }
            research_path = directory / "arrival-rolling-research.cbm"
            research.save_model(str(research_path))
            used_artifacts.append(research_path)
            _log("rolling_research_validated", target=target,
                 rmse_seconds=rolling_report["metrics"]["overall"]["methods"]["research_model"]["rmse_seconds"])
            del research, research_training, research_validation, raw, mask, research_values
            gc.collect()
        development_report["targets"][target] = {
            "selected_candidate": selected["name"], "selection_metric": config["primary_metric"],
            "candidates": candidates,
            "rolling_research": rolling_report,
        }
        write_json(repository_path(config["validation_report"], root), development_report)
        del training_rows, validation_rows, history, support
        gc.collect()
    trips_path = directory / "development-trips.json"
    write_json(trips_path, sorted(all_development_trips))
    used_artifacts.append(trips_path)
    development_report["completed_at"] = _now()
    validation_path = repository_path(config["validation_report"], root)
    write_json(validation_path, development_report)
    if sha256(config_path) != configuration_hash or sha256(manifest_path) != input_hash:
        raise ValueError("Experiment configuration or data changed during fitting.")
    if {str(path.relative_to(root)): sha256(path) for path in _code_paths(root)} != initial_code_hashes:
        raise ValueError("Experiment source code changed during fitting; no freeze was created.")
    paths = _code_paths(root) + used_artifacts + [config_path, manifest_path, validation_path,
                                                    root / "data/config/model-data.json"]
    frozen = seal({
        "experiment_version": config["experiment_version"], "frozen_at": _now(),
        "test_labels_opened": False, "configuration": config, "versions": _versions(),
        "feature_version": FEATURE_VERSION, "targets": target_artifacts,
        "development_trips_path": str(trips_path.relative_to(root)),
        "hashes": {str(path.relative_to(root)): sha256(path) for path in paths},
        "live_enabled": False, "evidence_class": config["evidence_class"],
    })
    write_json(frozen_path, frozen)
    write_json(root / "algo/reports/model-frozen.json", frozen)
    _log("experiment_frozen_before_test", path=str(frozen_path.relative_to(root)), sha256=sha256(frozen_path))
    return frozen_path


def promotion(metrics, config):
    """Apply the policy fixed before test, never thresholds chosen after results."""
    policy = config["promotion"]
    methods = metrics["overall"]["methods"]
    candidate = methods["model"]["rmse_seconds"]
    reasons = []
    required = policy["required_overall_rmse_improvement_seconds"]
    for reference in ("mta", "history"):
        if methods[reference]["rmse_seconds"] - candidate <= required:
            reasons.append("NO_OVERALL_RMSE_IMPROVEMENT_OVER_" + reference.upper())
    checked, insufficient = [], []
    for axis in policy["key_group_axes"]:
        for group, summary in metrics[axis].items():
            key = axis + ":" + group
            if summary["event_count"] < policy["key_group_min_events"]:
                insufficient.append(key)
                continue
            checked.append(key)
            for reference in ("mta", "history"):
                if (summary["methods"]["model"]["rmse_seconds"]
                        > summary["methods"][reference]["rmse_seconds"]
                        + policy["allowed_key_group_rmse_increase_seconds"]):
                    reasons.append("KEY_GROUP_RMSE_WORSENED:" + key + ":" + reference)
    return {"status": "RETAIN_BASELINE" if reasons else "PROVISIONAL_COMPONENT_IMPROVEMENT",
            "live_enabled": False, "failure_reasons": reasons, "checked_groups": checked,
            "insufficient_groups": insufficient,
            "limits": ["The labels are inferred MTA final-prediction proxies.",
                       "One training Saturday and Sunday do not establish general weekend performance.",
                       "Departure alert state is unavailable; disruption-specific departure performance is unvalidated.",
                       "No physical-arrival, destination-ETA or realized-savings claim is supported."]}


def evaluate(frozen_path, *, root=ROOT):
    from catboost import CatBoostRegressor
    root = Path(root).resolve()
    frozen_path = Path(frozen_path).resolve()
    frozen = verify_frozen(frozen_path, root=root)
    payload = frozen["payload"]
    if payload["versions"] != _versions():
        raise ValueError("Runtime versions differ from the frozen training environment.")
    config = payload["configuration"]
    report_path = repository_path(config["test_report"], root)
    if report_path.exists():
        previous = read_json(report_path)
        if previous["frozen_sha256"] != sha256(frozen_path):
            raise ValueError("An existing test report belongs to a different frozen experiment.")
        _log("returning_existing_test_report", path=str(report_path.relative_to(root)))
        return report_path
    manifest = read_json(repository_path(config["data_manifest"], root))
    development_trips = set(read_json(repository_path(payload["development_trips_path"], root)))
    report = {"experiment_version": payload["experiment_version"], "started_at": _now(),
              "split": "test", "frozen_sha256": sha256(frozen_path),
              "test_access_after_freeze": True, "targets": {}, "live_enabled": False,
              "evidence_class": config["evidence_class"], "versions": _versions(),
              "known_limitations": config["known_limitations"], "uncertainty": None}
    for target, details in payload["targets"].items():
        _log("opening_frozen_test_view", target=target)
        rows = load_rows(manifest, target, "test", allow_test=True, root=root)
        if development_trips & {row["trip_identity"] for row in rows}:
            raise ValueError("A service-qualified trip crosses development and test dates.")
        history = read_json(repository_path(details["history_path"], root))
        support = read_json(repository_path(details["support_path"], root))
        model = CatBoostRegressor()
        model.load_model(str(repository_path(details["model_path"], root)))
        values, applied = predictions(model, history, support, rows, target, details["feature_names"], config)
        metrics = evaluate_predictions(rows, values, model_applied={"model": applied})
        report["targets"][target] = {"selected_candidate": details["candidate"]["name"],
                                     "metrics": metrics, "adoption": promotion(metrics, config)}
        _log("frozen_test_target_complete", target=target,
             rmse={name: value["rmse_seconds"] for name, value in metrics["overall"]["methods"].items()},
             adoption=report["targets"][target]["adoption"]["status"])
        del rows, model, history, support, values
        gc.collect()
    report["completed_at"] = _now()
    verify_frozen(frozen_path, root=root)
    write_json(report_path, report)
    _log("frozen_test_complete", path=str(report_path.relative_to(root)))
    return report_path
