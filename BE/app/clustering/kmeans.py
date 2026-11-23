from math import isfinite
from statistics import mean

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


FEATURES = ["demand", "previous_month_change_pct", "previous_year_change_pct"]


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


def build_clustering_result(
    records: list[dict],
    max_k: int = 5,
) -> dict:
    """Cluster monthly demand observations using demand and growth features."""
    if not 2 <= max_k <= 8:
        raise ValueError("max_k must be between 2 and 8")

    demand_by_month: dict[str, float] = {}

    for record in records:
        month = record["month"]
        value = float(record["value"])

        if month in demand_by_month:
            raise ValueError(f"Duplicate month in dataset: {month}")

        if not isfinite(value) or value < 0:
            raise ValueError(f"Invalid demand value for {month}")

        demand_by_month[month] = value

    feature_rows = []

    for month in sorted(demand_by_month):
        demand = demand_by_month[month]
        previous_month = demand_by_month.get(_month_offset(month, -1))
        previous_year = demand_by_month.get(_month_offset(month, -12))

        # Growth percentages cannot be calculated if a comparison value is zero
        # or missing, so those months are excluded from the model.
        if previous_month is None or previous_year is None:
            continue
        if previous_month == 0 or previous_year == 0:
            continue

        feature_rows.append({
            "month": month,
            "demand": demand,
            "previous_month_change_pct": (
                (demand / previous_month) - 1
            ) * 100,
            "previous_year_change_pct": (
                (demand / previous_year) - 1
            ) * 100,
        })

    sample_count = len(feature_rows)
    if sample_count < 4:
        raise ValueError(
            "At least four months with valid month-over-month and "
            "year-over-year history are required"
        )

    feature_matrix = [
        [row[feature] for feature in FEATURES]
        for row in feature_rows
    ]

    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(feature_matrix)

    largest_k = min(max_k, sample_count - 1)
    candidate_results = []
    fitted_models = {}

    for k in range(2, largest_k + 1):
        model = KMeans(
            n_clusters=k,
            random_state=42,
            n_init=10,
        )
        raw_labels = model.fit_predict(scaled_features)
        score = silhouette_score(scaled_features, raw_labels)

        candidate_results.append({
            "k": k,
            "silhouette_score": round(float(score), 6),
            "inertia": round(float(model.inertia_), 6),
        })
        fitted_models[k] = (model, raw_labels)

    if not candidate_results:
        raise ValueError("Not enough data to evaluate K-Means clusters")

    # Prefer the smaller k if silhouette scores are equal.
    best_candidate = max(
        candidate_results,
        key=lambda candidate: (
            candidate["silhouette_score"],
            -candidate["k"],
        ),
    )
    selected_k = best_candidate["k"]
    model, raw_labels = fitted_models[selected_k]

    # K-Means cluster IDs have no inherent ordering. Reassign them by ascending
    # mean demand so that IDs are easier to compare and explain.
    raw_cluster_demand = {
        raw_cluster_id: mean(
            feature_rows[index]["demand"]
            for index, label in enumerate(raw_labels)
            if int(label) == raw_cluster_id
        )
        for raw_cluster_id in range(selected_k)
    }
    ordered_raw_ids = sorted(
        raw_cluster_demand,
        key=lambda cluster_id: raw_cluster_demand[cluster_id],
    )
    stable_cluster_ids = {
        raw_cluster_id: stable_id
        for stable_id, raw_cluster_id in enumerate(ordered_raw_ids)
    }

    assignments = []
    cluster_summaries = []

    for stable_id, raw_cluster_id in enumerate(ordered_raw_ids):
        members = [
            feature_rows[index]
            for index, label in enumerate(raw_labels)
            if int(label) == raw_cluster_id
        ]

        cluster_summaries.append({
            "cluster_id": stable_id,
            "label": _cluster_label(stable_id, selected_k),
            "month_count": len(members),
            "mean_demand": round(
                mean(row["demand"] for row in members), 4
            ),
            "min_demand": round(
                min(row["demand"] for row in members), 4
            ),
            "max_demand": round(
                max(row["demand"] for row in members), 4
            ),
            "mean_previous_month_change_pct": round(
                mean(row["previous_month_change_pct"] for row in members), 4
            ),
            "mean_previous_year_change_pct": round(
                mean(row["previous_year_change_pct"] for row in members), 4
            ),
        })

    for index, row in enumerate(feature_rows):
        raw_cluster_id = int(raw_labels[index])
        stable_id = stable_cluster_ids[raw_cluster_id]

        assignments.append({
            "month": row["month"],
            "cluster_id": stable_id,
            "cluster_label": _cluster_label(stable_id, selected_k),
            "demand": round(row["demand"], 4),
            "previous_month_change_pct": round(
                row["previous_month_change_pct"], 4
            ),
            "previous_year_change_pct": round(
                row["previous_year_change_pct"], 4
            ),
        })

    return {
        "method": "KMeans",
        "feature_names": FEATURES,
        "scaling": "StandardScaler",
        "selection_method": "highest_silhouette_score",
        "selected_k": selected_k,
        "silhouette_score": best_candidate["silhouette_score"],
        "candidate_scores": candidate_results,
        "sample_count": sample_count,
        "cluster_summaries": cluster_summaries,
        "assignments": assignments,
    }