from math import sqrt


FEATURES = ("demand", "previous_month", "previous_year")


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None

    x_values = [pair[0] for pair in pairs]
    y_values = [pair[1] for pair in pairs]

    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)

    numerator = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in pairs
    )
    x_sum_squares = sum((x - x_mean) ** 2 for x in x_values)
    y_sum_squares = sum((y - y_mean) ** 2 for y in y_values)

    denominator = sqrt(x_sum_squares * y_sum_squares)
    if denominator == 0:
        return None

    return round(numerator / denominator, 6)


def build_correlation(records: list[dict]) -> dict:
    demand_by_month = {
        record["month"]: float(record["value"])
        for record in records
    }

    observations = []

    for record in records:
        month = record["month"]
        year, month_number = (int(part) for part in month.split("-"))

        previous_month_number = month_number - 1
        previous_month_year = year

        if previous_month_number == 0:
            previous_month_number = 12
            previous_month_year -= 1

        previous_month = (
            f"{previous_month_year:04d}-{previous_month_number:02d}"
        )
        previous_year = f"{year - 1:04d}-{month_number:02d}"

        observations.append({
            "demand": demand_by_month[month],
            "previous_month": demand_by_month.get(previous_month),
            "previous_year": demand_by_month.get(previous_year),
        })

    matrix = {}
    pair_counts = {}

    for left_feature in FEATURES:
        matrix[left_feature] = {}
        pair_counts[left_feature] = {}

        for right_feature in FEATURES:
            pairs = [
                (observation[left_feature], observation[right_feature])
                for observation in observations
                if observation[left_feature] is not None
                and observation[right_feature] is not None
            ]

            matrix[left_feature][right_feature] = _pearson(pairs)
            pair_counts[left_feature][right_feature] = len(pairs)

    return {
        "method": "pearson",
        "features": list(FEATURES),
        "matrix": matrix,
        "pair_counts": pair_counts,
    }