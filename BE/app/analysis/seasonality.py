from collections import defaultdict
from statistics import mean, median


def build_seasonality(records: list[dict]) -> dict:
    values_by_month_number: dict[int, list[float]] = defaultdict(list)

    for record in records:
        month_number = int(record["month"].split("-")[1])
        values_by_month_number[month_number].append(float(record["value"]))

    months = []

    for month_number in range(1, 13):
        values = values_by_month_number[month_number]

        months.append({
            "month_number": month_number,
            "count": len(values),
            "mean": round(mean(values), 4) if values else None,
            "median": round(median(values), 4) if values else None,
            "min": round(min(values), 4) if values else None,
            "max": round(max(values), 4) if values else None,
        })

    return {
        "method": "group_by_calendar_month",
        "records": months,
    }