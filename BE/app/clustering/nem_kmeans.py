"""K-Means training and inference for daily Open Electricity NEM observations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
from pathlib import Path
from statistics import mean
from typing import Any
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import RobustScaler, StandardScaler



NEM_ARTIFACT_VERSION = 1
NEM_CONTRACT_VERSION = 1
NEM_SCALERS = ("standard", "robust")
STABILITY_SEEDS = (7, 21, 42, 84, 126)
MIN_CLUSTER_FRACTION = 0.03


class NEMClusteringArtifactError(ValueError):
    """An NEM clustering artifact cannot be used with the supplied dataset."""


def nem_artifact_path() -> Path:
    configured = os.getenv("NEM_CLUSTERING_MODEL_PATH")
    if configured:
        return Path(configured)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_nem_daily_kmeans.joblib"


def _fingerprint(dataset: dict[str, Any], feature_names: list[str], feature_units: dict[str, str], records: list[dict[str, Any]]) -> str:
    canonical_data = {
        "dataset_id": dataset["dataset_id"],
        "dataset_name": dataset["dataset_name"],
        "dataset_source": dataset["dataset_source"],
        "network_code": dataset["network_code"],
        "interval": dataset["interval"],
        "feature_names": feature_names,
        "feature_units": feature_units,
        "records": records,
    }
    encoded = json.dumps(canonical_data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validated_configuration(request: Any, key: str) -> dict[str, Any]:
    dataset = {
        "dataset_id": request.dataset_id,
        "dataset_name": request.dataset_name,
        "dataset_source": request.dataset_source,
        "network_code": request.network_code,
        "interval": request.interval,
    }
    configuration = request.configurations[key].model_dump(mode="json")
    actual = _fingerprint(
        dataset,
        configuration["feature_names"],
        configuration["feature_units"],
        configuration["records"],
    )
    if actual != configuration["data_fingerprint"]:
        raise ValueError(f"Model {key} data fingerprint does not match its records")
    return configuration


def _scaler(name: str):
    if name == "standard":
        return StandardScaler()
    if name == "robust":
        return RobustScaler()
    raise ValueError("scaler must be standard or robust")


def _matrix(configuration: dict[str, Any]) -> np.ndarray:
    matrix = np.asarray(
        [[record["features"][name] for name in configuration["feature_names"]] for record in configuration["records"]],
        dtype=float,
    )
    if matrix.ndim != 2 or not matrix.shape[0] or not matrix.shape[1]:
        raise ValueError("daily NEM feature configuration contains no records")
    if not np.isfinite(matrix).all():
        raise ValueError("daily NEM feature values must all be finite")
    return matrix


def _contiguous_blocks(sample_count: int, minimum_samples: int) -> list[np.ndarray]:
    block_size = max(minimum_samples, int(math.ceil(sample_count * 0.8)))
    block_size = min(block_size, sample_count)
    starts = sorted({int(round(value)) for value in np.linspace(0, sample_count - block_size, num=5)})
    return [np.arange(start, start + block_size) for start in starts]


def _evaluate_candidate(matrix: np.ndarray, k: int, scaler_name: str) -> tuple[dict[str, Any], Any, Any, np.ndarray]:
    scaler = _scaler(scaler_name)
    scaled = scaler.fit_transform(matrix)
    full_model = KMeans(n_clusters=k, random_state=42, n_init=10)
    full_labels = full_model.fit_predict(scaled)
    if len(set(int(label) for label in full_labels)) < 2:
        raise ValueError("K-Means produced fewer than two populated clusters")
    score = float(silhouette_score(scaled, full_labels))
    cluster_sizes = np.bincount(full_labels, minlength=k).astype(int)

    seed_labels = []
    for seed in STABILITY_SEEDS:
        seeded = KMeans(n_clusters=k, random_state=seed, n_init=10)
        labels = seeded.fit_predict(scaled)
        seed_labels.append(labels)
    seed_ari = [
        float(adjusted_rand_score(seed_labels[0], other))
        for other in seed_labels[1:]
    ]

    block_ari = []
    for indices in _contiguous_blocks(len(matrix), k + 1):
        block_scaler = _scaler(scaler_name)
        block_scaled = block_scaler.fit_transform(matrix[indices])
        if len(indices) <= k:
            continue
        block_model = KMeans(n_clusters=k, random_state=42, n_init=10)
        block_model.fit(block_scaled)
        resampled_labels = block_model.predict(block_scaler.transform(matrix))
        block_ari.append(float(adjusted_rand_score(full_labels, resampled_labels)))

    seed_stability = mean(seed_ari) if seed_ari else 1.0
    block_stability = mean(block_ari) if block_ari else 1.0
    stability = (seed_stability + block_stability) / 2
    minimum_size = max(2, int(math.ceil(len(matrix) * MIN_CLUSTER_FRACTION)))
    result = {
        "k": k,
        "scaler": scaler_name,
        "silhouette_score": round(score, 6),
        "seed_stability_mean_ari": round(seed_stability, 6),
        "block_stability_mean_ari": round(block_stability, 6),
        "stability_mean_ari": round(stability, 6),
        "cluster_sizes": [int(value) for value in cluster_sizes],
        "minimum_cluster_size": int(cluster_sizes.min()),
        "minimum_cluster_size_required": minimum_size,
        "eligible_for_selection": bool(cluster_sizes.min() >= minimum_size),
        "selection_score": round(0.5 * score + 0.5 * stability, 6),
        "time_block_resamples": len(block_ari),
    }
    return result, scaler, full_model, full_labels


def _stable_cluster_ids(model: KMeans, scaler: Any) -> dict[int, int]:
    original_centers = scaler.inverse_transform(model.cluster_centers_)
    ordered = sorted(
        range(len(original_centers)),
        key=lambda cluster_id: tuple(float(value) for value in original_centers[cluster_id]),
    )
    return {raw: stable for stable, raw in enumerate(ordered)}


def train_nem_clustering(request: Any, *, max_k: int = 5) -> dict[str, Any]:
    """Evaluate Models A/B and persist the best eligible NEM artifact."""
    if not 2 <= max_k <= 5:
        raise ValueError("max_k must be between 2 and 5")

    evaluations = []
    fitted: dict[tuple[str, str, int], tuple[Any, Any, np.ndarray]] = {}
    configurations: dict[str, dict[str, Any]] = {}
    for config_name in ("A", "B"):
        configuration = _validated_configuration(request, config_name)
        configurations[config_name] = configuration
        matrix = _matrix(configuration)
        if len(matrix) < max_k + 1:
            raise ValueError(f"Model {config_name} requires at least {max_k + 1} daily records")
        for scaler_name in NEM_SCALERS:
            for k in range(2, min(max_k, len(matrix) - 1) + 1):
                result, scaler, model, labels = _evaluate_candidate(matrix, k, scaler_name)
                result["feature_set"] = config_name
                result["sample_count"] = len(matrix)
                evaluations.append(result)
                fitted[(config_name, scaler_name, k)] = (scaler, model, labels)

    eligible = [item for item in evaluations if item["eligible_for_selection"]]
    if not eligible:
        raise ValueError("No evaluated clustering candidate meets the minimum cluster-size requirement")
    selected = max(
        eligible,
        key=lambda item: (
            item["selection_score"],
            item["stability_mean_ari"],
            item["silhouette_score"],
            -item["k"],
        ),
    )
    selected_key = (selected["feature_set"], selected["scaler"], selected["k"])
    scaler, model, labels = fitted[selected_key]
    configuration = configurations[selected["feature_set"]]
    mapping = _stable_cluster_ids(model, scaler)
    original_centers = scaler.inverse_transform(model.cluster_centers_)
    stable_centroids = [None] * selected["k"]
    for raw_cluster, stable_cluster in mapping.items():
        stable_centroids[stable_cluster] = {
            feature: float(value)
            for feature, value in zip(configuration["feature_names"], original_centers[raw_cluster])
        }
    matrix = _matrix(configuration)
    lower = matrix.min(axis=0)
    upper = matrix.max(axis=0)
    metric_quality = configuration["metric_quality"]
    trained_at = datetime.now(timezone.utc).isoformat()
    model_parameters = {
        "selected_k": int(selected["k"]),
        "scaler": selected["scaler"],
        "n_init": 10,
        "random_state": 42,
        "candidate_k_min": 2,
        "candidate_k_max": int(max_k),
        "candidate_scalers": list(NEM_SCALERS),
        "stability_seeds": list(STABILITY_SEEDS),
        "minimum_cluster_fraction": MIN_CLUSTER_FRACTION,
    }
    artifact = {
        "artifact_version": NEM_ARTIFACT_VERSION,
        "contract_version": NEM_CONTRACT_VERSION,
        "algorithm": "KMeans",
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "trained_at": trained_at,
        "model_parameters": model_parameters,
        "dataset": {
            "dataset_id": request.dataset_id,
            "dataset_name": request.dataset_name,
            "dataset_source": request.dataset_source,
            "network_code": request.network_code,
            "interval": request.interval,
        },
        "feature_set": selected["feature_set"],
        "feature_names": configuration["feature_names"],
        "feature_units": configuration["feature_units"],
        "training_start": configuration["start_date"],
        "training_end": configuration["end_date"],
        "training_observation_count": configuration["observation_count"],
        "training_data_fingerprint": configuration["data_fingerprint"],
        "scaler_name": selected["scaler"],
        "scaler": scaler,
        "model": model,
        "selected_k": selected["k"],
        "raw_to_stable": mapping,
        "centroids_original_units": stable_centroids,
        "training_feature_min": {name: float(value) for name, value in zip(configuration["feature_names"], lower)},
        "training_feature_max": {name: float(value) for name, value in zip(configuration["feature_names"], upper)},
        "silhouette_score": selected["silhouette_score"],
        "stability": {
            "seed_mean_ari": selected["seed_stability_mean_ari"],
            "time_block_mean_ari": selected["block_stability_mean_ari"],
            "combined_mean_ari": selected["stability_mean_ari"],
            "time_block_resamples": selected["time_block_resamples"],
        },
        "selection_method": "highest_balanced_silhouette_and_stability_after_minimum_cluster_size_filter",
        "minimum_cluster_fraction": MIN_CLUSTER_FRACTION,
        "candidate_evaluations": evaluations,
        "metric_quality": metric_quality,
    }
    path = nem_artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    try:
        joblib.dump(artifact, temporary_path)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)

    stable_labels = [mapping[int(label)] for label in labels]
    sizes = np.bincount(stable_labels, minlength=selected["k"]).astype(int)
    return {
        "stage": "training",
        "model_name": "KMeans",
        "feature_set": selected["feature_set"],
        "feature_names": configuration["feature_names"],
        "feature_units": configuration["feature_units"],
        "selected_k": selected["k"],
        "scaler": selected["scaler"],
        "silhouette_score": selected["silhouette_score"],
        "stability": artifact["stability"],
        "cluster_sizes": [int(value) for value in sizes],
        "centroids_original_units": stable_centroids,
        "candidate_evaluations": evaluations,
        "selection_method": artifact["selection_method"],
        "minimum_cluster_fraction": MIN_CLUSTER_FRACTION,
        "sample_count": configuration["observation_count"],
        "training_start": configuration["start_date"],
        "training_end": configuration["end_date"],
        "training_data_fingerprint": configuration["data_fingerprint"],
        "data_quality": metric_quality,
        "artifact_name": path.name,
        "model_provenance": {
            "model_type": "clustering",
            "model_name": "KMeans",
            "artifact_name": path.name,
            "artifact_format": "joblib",
            "artifact_version": NEM_ARTIFACT_VERSION,
            "contract_version": NEM_CONTRACT_VERSION,
            "python_version": artifact["python_version"],
            "sklearn_version": artifact["sklearn_version"],
            "trained_at": trained_at,
            "model_parameters": model_parameters,
        },
        "cluster_label_semantics": "Groups of days with similar network-level operating characteristics; not geographic regions.",
    }


def _cluster_summaries(configuration: dict[str, Any], labels: list[int], k: int) -> list[dict[str, Any]]:
    summaries = []
    for cluster_id in range(k):
        members = [record for record, label in zip(configuration["records"], labels) if label == cluster_id]
        if not members:
            summaries.append({"cluster_id": cluster_id, "label": f"Cluster {cluster_id + 1}", "day_count": 0, "feature_means": {}})
            continue
        means = {
            name: mean(record["features"][name] for record in members)
            for name in configuration["feature_names"]
        }
        summaries.append({
            "cluster_id": cluster_id,
            "label": f"Cluster {cluster_id + 1}",
            "day_count": len(members),
            "feature_means": means,
        })
    return summaries


def run_nem_clustering(request: Any) -> dict[str, Any]:
    """Load the saved artifact and assign daily observations without fitting."""
    path = nem_artifact_path()
    if not path.is_file():
        raise FileNotFoundError("NEM clustering artifact is missing. An Admin must train the model before running it.")
    try:
        artifact = joblib.load(path)
    except Exception as exc:
        raise NEMClusteringArtifactError("NEM clustering artifact cannot be loaded") from exc
    if not isinstance(artifact, dict) or artifact.get("artifact_version") != NEM_ARTIFACT_VERSION:
        raise NEMClusteringArtifactError("NEM clustering artifact version is incompatible")
    expected_dataset = {
        "dataset_id": request.dataset_id,
        "dataset_name": request.dataset_name,
        "dataset_source": request.dataset_source,
        "network_code": request.network_code,
        "interval": request.interval,
    }
    if artifact.get("dataset") != expected_dataset:
        raise NEMClusteringArtifactError("NEM clustering artifact belongs to a different dataset identity")
    feature_set = artifact.get("feature_set")
    if feature_set not in request.configurations:
        raise NEMClusteringArtifactError("NEM clustering artifact feature set is unavailable")
    configuration = _validated_configuration(request, feature_set)
    if artifact.get("feature_names") != configuration["feature_names"]:
        raise NEMClusteringArtifactError("NEM clustering artifact feature names or order do not match current data")
    if artifact.get("feature_units") != configuration["feature_units"]:
        raise NEMClusteringArtifactError("NEM clustering artifact feature units do not match current data")
    if not all(key in artifact for key in ("scaler", "model", "raw_to_stable", "selected_k", "training_data_fingerprint")):
        raise NEMClusteringArtifactError("NEM clustering artifact is incomplete")
    if not configuration["records"]:
        raise ValueError(f"Model {feature_set} has no complete daily records to run")

    matrix = _matrix(configuration)
    scaled = artifact["scaler"].transform(matrix)
    raw_labels = artifact["model"].predict(scaled)
    mapping = artifact["raw_to_stable"]
    labels = [int(mapping[int(label)]) for label in raw_labels]
    assignments = []
    for record, cluster_id in zip(configuration["records"], labels):
        assignments.append({
            "date": record["date"],
            "cluster_id": cluster_id,
            "cluster_label": f"Cluster {cluster_id + 1}",
            "features": record["features"],
        })

    out_of_range = {}
    for index, name in enumerate(configuration["feature_names"]):
        lower = artifact["training_feature_min"][name]
        upper = artifact["training_feature_max"][name]
        out_of_range[name] = int(np.count_nonzero((matrix[:, index] < lower) | (matrix[:, index] > upper)))
    return {
        "stage": "run",
        "method": "KMeans",
        "feature_set": feature_set,
        "feature_names": configuration["feature_names"],
        "feature_units": configuration["feature_units"],
        "scaler": artifact["scaler_name"],
        "selected_k": artifact["selected_k"],
        "silhouette_score": artifact["silhouette_score"],
        "training_data_fingerprint": artifact["training_data_fingerprint"],
        "run_data_fingerprint": configuration["data_fingerprint"],
        "training_start": artifact["training_start"],
        "training_end": artifact["training_end"],
        "run_start": configuration["start_date"],
        "run_end": configuration["end_date"],
        "training_observation_count": artifact["training_observation_count"],
        "run_observation_count": configuration["observation_count"],
        "out_of_training_range_counts": out_of_range,
        "drift_warning": any(out_of_range.values()),
        "centroids_original_units": artifact["centroids_original_units"],
        "cluster_summaries": _cluster_summaries(configuration, labels, int(artifact["selected_k"])),
        "assignments": assignments,
        "cluster_label_semantics": "Groups of days with similar network-level operating characteristics; not geographic regions.",
        "artifact_name": path.name,
    }
