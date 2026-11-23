from statistics import median


def build_summary(records: list[dict]) -> dict:
    values = [float(record["value"]) for record in records]

    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
        }

    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 4),
        "median": round(median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }