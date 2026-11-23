from statistics import mean


def _month_offset(month: str, offset: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    absolute_month = year * 12 + month_number - 1 + offset
    result_year, result_month = divmod(absolute_month, 12)
    return f"{result_year:04d}-{result_month + 1:02d}"


def build_trend(records: list[dict], window_months: int = 12) -> dict:
    """Calculate a trailing rolling mean as the monthly trend estimate."""
    values_by_month = {
        record["month"]: float(record["value"])
        for record in records
    }

    series = []

    for record in records:
        month = record["month"]
        window_months_in_data = [
            values_by_month.get(_month_offset(month, -offset))
            for offset in reversed(range(window_months))
        ]

        trend_value = (
            mean(window_months_in_data)
            if all(value is not None for value in window_months_in_data)
            else None
        )

        series.append({
            "month": month,
            "value": float(record["value"]),
            "trend": round(trend_value, 4) if trend_value is not None else None,
        })

    return {
        "window_months": window_months,
        "method": "trailing_rolling_mean",
        "records": series,
    }