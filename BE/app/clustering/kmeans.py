import hashlib
import json
import os
from math import isfinite
from pathlib import Path
from statistics import mean

import joblib
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


FEATURES = ["demand", "previous_month_change_pct", "previous_year_change_pct"]
ARTIFACT_VERSION = 1


class ArtifactCompatibilityError(ValueError):
    """Raised when a saved model cannot safely be applied to current data."""


def artifact_path() -> Path:
    configured_path = os.getenv("CLUSTERING_MODEL_PATH")
    if configured_path:
        return Path(configured_path)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "artifacts" / "electricity_demand_kmeans.joblib"


def _month_offset(month: str, offset: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    absolute_month = year * 12 + month_number - 1 + offset
    result_year, result_month = divmod(absolute_month, 12)
    return f"{result_year:04d}-{result_month + 1:02d}"


def _cluster_label(cluster_number: int, cluster_count: int) -> str:
    if cluster_count == 2:
        labels = ["Nhu cầu thấp hơn", "Nhu cầu cao hơn"]
        return labels[cluster_number]
    if cluster_count == 3:
        labels = ["Nhu cầu thấp", "Nhu cầu trung bình", "Nhu cầu cao"]
        return labels[cluster_number]
    return f"Nhóm {cluster_number + 1} (xếp theo nhu cầu trung bình)"


def _build_features(records: list[dict]) -> tuple[list[dict], str]:
    demand_by_month: dict[str, float] = {}
    for record in records:
        month = record["month"]
        value = float(record["value"])
        if month in demand_by_month:
            raise ValueError(f"Duplicate month in dataset: {month}")
        if not isfinite(value) or value < 0:
            raise ValueError(f"Invalid demand value for {month}")
        demand_by_month[month] = value

    if not demand_by_month:
        raise ValueError("No demand records are available")

    feature_rows = []
    for month in sorted(demand_by_month):
        demand = demand_by_month[month]
        previous_month = demand_by_month.get(_month_offset(month, -1))
        previous_year = demand_by_month.get(_month_offset(month, -12))
        if previous_month is None or previous_year is None or previous_month == 0 or previous_year == 0:
            continue
        feature_rows.append({
            "month": month,
            "demand": demand,
            "previous_month_change_pct": (demand / previous_month - 1) * 100,
            "previous_year_change_pct": (demand / previous_year - 1) * 100,
        })
    if len(feature_rows) < 4:
        raise ValueError("At least four months with valid month-over-month and year-over-year history are required")

    fingerprint_payload = sorted(demand_by_month.items())
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, separators=(",", ":")).encode()).hexdigest()
    return feature_rows, fingerprint


def _fit_artifact(feature_rows: list[dict], max_k: int, fingerprint: str) -> tuple[dict, dict]:
    if not 2 <= max_k <= 8:
        raise ValueError("max_k must be between 2 and 8")
    matrix = [[row[name] for name in FEATURES] for row in feature_rows]
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    largest_k = min(max_k, len(feature_rows) - 1)
    candidates = []
    fitted = {}
    for k in range(2, largest_k + 1):
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(scaled)
        score = silhouette_score(scaled, labels)
        candidates.append({"k": k, "silhouette_score": round(float(score), 6), "inertia": round(float(model.inertia_), 6)})
        fitted[k] = (model, labels)
    if not candidates:
        raise ValueError("Not enough data to evaluate K-Means clusters")
    best = max(candidates, key=lambda candidate: (candidate["silhouette_score"], -candidate["k"]))
    selected_k = best["k"]
    model, labels = fitted[selected_k]
    mean_by_id = {
        cluster_id: mean(row["demand"] for row, label in zip(feature_rows, labels) if int(label) == cluster_id)
        for cluster_id in range(selected_k)
    }
    ordered_ids = sorted(mean_by_id, key=mean_by_id.get)
    raw_to_stable = {raw_id: stable_id for stable_id, raw_id in enumerate(ordered_ids)}
    artifact = {
        "artifact_version": ARTIFACT_VERSION,
        "model_name": "KMeans",
        "scaler": scaler,
        "model": model,
        "feature_names": FEATURES,
        "selected_k": selected_k,
        "raw_to_stable": raw_to_stable,
        "trained_through_month": feature_rows[-1]["month"],
        "data_fingerprint": fingerprint,
        "candidate_scores": candidates,
    }
    training_metrics = {
        "stage": "training",
        "model_name": "KMeans",
        "trained_through_month": feature_rows[-1]["month"],
        "selected_k": selected_k,
        "silhouette_score": best["silhouette_score"],
        "candidate_scores": candidates,
        "sample_count": len(feature_rows),
        "artifact_name": artifact_path().name,
    }
    return artifact, training_metrics


def train_and_save_model(records: list[dict], max_k: int = 5) -> dict:
    """Fit scaler and K-Means on monthly history, then atomically persist them."""
    rows, fingerprint = _build_features(records)
    artifact, metrics = _fit_artifact(rows, max_k, fingerprint)
    path = artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    try:
        joblib.dump(artifact, temporary_path)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return metrics


def build_clustering_result(records: list[dict]) -> dict:
    """Load a prebuilt clustering artifact and label the matching monthly data."""
    rows, fingerprint = _build_features(records)
    path = artifact_path()
    if not path.is_file():
        raise FileNotFoundError("Clustering model artifact is missing. Call POST /api/clustering/train before run.")
    try:
        artifact = joblib.load(path)
    except Exception as exc:
        raise ArtifactCompatibilityError("Clustering model artifact cannot be loaded. Train the clustering model again.") from exc
    if not isinstance(artifact, dict) or artifact.get("artifact_version") != ARTIFACT_VERSION or artifact.get("feature_names") != FEATURES:
        raise ArtifactCompatibilityError("Clustering model artifact format is incompatible. Train the clustering model again.")
    if not all(key in artifact for key in ("scaler", "model", "selected_k", "raw_to_stable", "candidate_scores", "trained_through_month", "data_fingerprint")):
        raise ArtifactCompatibilityError("Clustering model artifact is incomplete. Train the clustering model again.")
    latest_month = rows[-1]["month"]
    if latest_month != artifact.get("trained_through_month"):
        raise ArtifactCompatibilityError(f"Clustering model is stale. Latest data month is {latest_month}; artifact trained through {artifact.get('trained_through_month')}. Train the model again.")
    if fingerprint != artifact.get("data_fingerprint"):
        raise ArtifactCompatibilityError("Clustering model was built from different source data. Train the model again.")

    matrix = [[row[name] for name in FEATURES] for row in rows]
    scaled = artifact["scaler"].transform(matrix)
    model = artifact["model"]
    raw_labels = model.predict(scaled)
    selected_k = int(artifact["selected_k"])
    raw_to_stable = artifact["raw_to_stable"]
    assignments = []
    summaries = []
    for stable_id in range(selected_k):
        members = [row for row, label in zip(rows, raw_labels) if raw_to_stable[int(label)] == stable_id]
        summaries.append({
            "cluster_id": stable_id,
            "label": _cluster_label(stable_id, selected_k),
            "month_count": len(members),
            "mean_demand": round(mean(row["demand"] for row in members), 4),
            "min_demand": round(min(row["demand"] for row in members), 4),
            "max_demand": round(max(row["demand"] for row in members), 4),
            "mean_previous_month_change_pct": round(mean(row["previous_month_change_pct"] for row in members), 4),
            "mean_previous_year_change_pct": round(mean(row["previous_year_change_pct"] for row in members), 4),
        })
    for row, raw_id in zip(rows, raw_labels):
        stable_id = raw_to_stable[int(raw_id)]
        assignments.append({
            "month": row["month"], "cluster_id": stable_id,
            "cluster_label": _cluster_label(stable_id, selected_k),
            "demand": round(row["demand"], 4),
            "previous_month_change_pct": round(row["previous_month_change_pct"], 4),
            "previous_year_change_pct": round(row["previous_year_change_pct"], 4),
        })
    return {
        "stage": "run", "method": "KMeans", "feature_names": FEATURES,
        "scaling": "StandardScaler", "selection_method": "highest_silhouette_score",
        "selected_k": selected_k, "silhouette_score": next(item["silhouette_score"] for item in artifact["candidate_scores"] if item["k"] == selected_k),
        "candidate_scores": artifact["candidate_scores"], "sample_count": len(rows),
        "trained_through_month": latest_month, "cluster_summaries": summaries,
        "assignments": assignments, "artifact_name": path.name,
    }
