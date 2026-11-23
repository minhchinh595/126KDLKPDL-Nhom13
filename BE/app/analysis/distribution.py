def build_distribution(records: list[dict], bins: int = 10) -> dict:
    """Build a histogram with the same bin boundaries as the public API."""
    if not 2 <= bins <= 50:
        raise ValueError("bins must be between 2 and 50")

    values = [float(record["value"]) for record in records]
    if not values:
        return {"count": 0, "bins": []}

    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return {
            "count": len(values),
            "bins": [{"start": minimum, "end": maximum, "count": len(values)}],
        }

    width = (maximum - minimum) / bins
    histogram = []
    for index in range(bins):
        bin_start = minimum + index * width
        bin_end = maximum if index == bins - 1 else minimum + (index + 1) * width
        if index == bins - 1:
            count = sum(bin_start <= value <= bin_end for value in values)
        else:
            count = sum(bin_start <= value < bin_end for value in values)
        histogram.append({"start": round(bin_start, 4), "end": round(bin_end, 4), "count": count})

    return {"count": len(values), "bins": histogram}
