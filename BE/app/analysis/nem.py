"""Deterministic descriptive analytics over NEM-local daily observations."""

from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import date, datetime, timedelta
from math import sqrt
from statistics import mean, median
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Australia/Brisbane")
DAILY_METRICS = ("demand", "price", "demand_energy", "generation_renewable", "renewable_proportion")


def _daily_values(records: list[dict], metric: str = "demand") -> dict[date, float]:
    values = {}
    for row in records:
        ts = datetime.fromisoformat(row["observed_at"])
        if ts.tzinfo is None:
            raise ValueError("NEM timestamps must include a timezone")
        if row["metric"] == metric and row["interval"] == "1d" and row["grouping_type"] == "network" and row["grouping_code"] == "":
            day = ts.astimezone(TZ).date()
            if day in values:
                raise ValueError(f"multiple {metric} daily series exist for {day.isoformat()}")
            values[day] = float(row["value"])
    return values


def trend(records: list[dict], view: str, metric: str = "demand") -> dict:
    if view not in {"day", "week", "month"}:
        raise ValueError("view must be day, week, or month")
    if metric not in DAILY_METRICS:
        raise ValueError("trend metric must be a supported daily NEM metric")
    daily = _daily_values(records, metric)
    weights = _daily_values(records, "demand_energy") if metric == "price" else {}
    units = {row["metric"]: row["unit"] for row in records if row["interval"] == "1d"}
    buckets: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for day, value in sorted(daily.items()):
        if view == "day": key = day.isoformat()
        elif view == "week": key = (day - timedelta(days=day.weekday())).isoformat()
        else: key = day.strftime("%Y-%m")
        buckets[key].append((day, value))
    unit = units.get(metric, {"demand": "MW", "price": "$/MWh", "demand_energy": "MWh", "generation_renewable": "MW", "renewable_proportion": "%"}[metric])
    if not daily:
        return {"metric": metric, "unit": unit, "view": view, "aggregation": "No source observations in the selected range.", "records": []}
    first, last = min(daily), max(daily)
    periods = []
    if view == "day":
        cursor = first
        while cursor <= last:
            periods.append((cursor.isoformat(), cursor, cursor + timedelta(days=1)))
            cursor += timedelta(days=1)
    elif view == "week":
        cursor = first - timedelta(days=first.weekday())
        last_start = last - timedelta(days=last.weekday())
        while cursor <= last_start:
            periods.append((cursor.isoformat(), cursor, cursor + timedelta(days=7)))
            cursor += timedelta(days=7)
    else:
        cursor = first.replace(day=1)
        while cursor <= last.replace(day=1):
            next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            periods.append((cursor.strftime("%Y-%m"), cursor, next_month))
            cursor = next_month
    points = []
    for key, period_start, period_end in periods:
        items = [(day, value) for day, value in daily.items() if period_start <= day < period_end]
        expected = (period_end - period_start).days
        if view in {"week", "month"} and period_start < first:
            expected -= (first - period_start).days
        if view in {"week", "month"} and period_end - timedelta(days=1) > last:
            expected -= (period_end - timedelta(days=1) - last).days
        weighted_count = None
        if metric == "demand_energy": value = sum(v for _, v in items) if items else None
        elif metric == "price" and view != "day":
            weighted = [(v, weights[day]) for day, v in items if day in weights and weights[day] > 0]
            value = sum(v*w for v, w in weighted) / sum(w for _, w in weighted) if weighted else None
            weighted_count = len(weighted)
        elif metric == "renewable_proportion" and view != "day": value = None
        else: value = mean(v for _, v in items) if items else None
        coverage_count = weighted_count if weighted_count is not None else len(items)
        points.append({"period": key, "value": value, "sample_count": len(items), "weighted_sample_count": weighted_count, "expected_days": expected, "coverage_fraction": coverage_count / expected if expected else None})
    if metric in {"demand", "generation_renewable"}:
        aggregation = "Mean of observed daily rates; daily completeness inside each day is unavailable, and coverage_fraction counts observed calendar days only."
    elif metric == "demand_energy": aggregation = "Sum of available daily MWh; missing calendar days remain visible in coverage and are not imputed."
    elif metric == "price": aggregation = "For week/month, daily prices are weighted by same-date demand_energy (MWh); periods without positive weights return null. Daily view retains source prices."
    elif view == "day": aggregation = "Daily source-provided renewable proportion; no resampling performed."
    else: aggregation = "Not aggregated: correct multi-day renewable proportion requires correctly aggregated renewable and gross-demand energy, which is unavailable in this record set."
    return {"metric": metric, "unit": unit, "view": view, "aggregation": aggregation, "records": points}


def seasonality(records: list[dict]) -> dict:
    daily = _daily_values(records)
    groups: dict[int, list[float]] = defaultdict(list)
    for day, value in daily.items(): groups[day.isoweekday()].append(value)
    return {"metric": "demand", "unit": "MW", "method": "weekday exploratory mean", "limitation": "Only about one year is available; this is exploratory and does not establish reliable annual seasonality.", "records": [{"weekday": i, "count": len(groups[i]), "mean": mean(groups[i]) if groups[i] else None} for i in range(1, 8)]}


def correlation(records: list[dict]) -> dict:
    by_metric = {metric: _daily_values(records, metric) for metric in DAILY_METRICS}
    dates = sorted(set.intersection(*(set(v) for v in by_metric.values()))) if by_metric else []
    matrix, counts, metadata = {}, {}, {}
    units = {row["metric"]: row["unit"] for row in records if row["interval"] == "1d"}
    for a in DAILY_METRICS:
        matrix[a], counts[a] = {}, {}
        metadata[a] = {"unit": units.get(a)}
        for b in DAILY_METRICS:
            pairs = [(by_metric[a][d], by_metric[b][d]) for d in dates]
            counts[a][b] = len(pairs)
            if len(pairs) < 2: matrix[a][b] = None; continue
            xs, ys = zip(*pairs)
            mx, my = mean(xs), mean(ys)
            den = sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
            matrix[a][b] = sum((x-mx)*(y-my) for x,y in pairs) / den if den else None
    return {"metrics": metadata, "alignment": "same Australia/Brisbane calendar date; network grouping only", "sample_dates": len(dates), "matrix": matrix, "pair_counts": counts}


def distribution(records: list[dict], metric: str, interval: str, bins: int) -> dict:
    rows = [r for r in records if r["metric"] == metric and r["interval"] == interval]
    values = [float(r["value"]) for r in rows]
    unit = rows[0]["unit"] if rows else None
    if not values: return {"metric": metric, "interval": interval, "unit": unit, "sample_count": 0, "bins": []}
    low, high = min(values), max(values)
    width = (high - low) / bins if high != low else 1.0
    result = [{"start": low + i*width, "end": low + (i+1)*width, "count": 0} for i in range(bins)]
    for value in values: result[min(int((value-low)/width), bins-1)]["count"] += 1
    return {"metric": metric, "interval": interval, "unit": unit, "sample_count": len(values), "bins": result}


def scatter(records: list[dict], x_metric: str, y_metric: str) -> dict:
    if x_metric not in DAILY_METRICS or y_metric not in DAILY_METRICS:
        raise ValueError("scatter metrics must be supported daily NEM metrics")
    xs, ys = _daily_values(records, x_metric), _daily_values(records, y_metric)
    dates = sorted(set(xs) & set(ys))
    metadata = {}
    for row in records:
        if row["metric"] in (x_metric, y_metric): metadata[row["metric"]] = {"unit": row["unit"], "interval": row["interval"]}
    return {"x": {"metric": x_metric, **metadata.get(x_metric, {})}, "y": {"metric": y_metric, **metadata.get(y_metric, {})}, "sample_count": len(dates), "points": [{"date": d.isoformat(), "x": xs[d], "y": ys[d]} for d in dates]}


def summary(records: list[dict]) -> dict:
    values = _daily_values(records)
    xs = list(values.values())
    return {"metric": "demand", "interval": "1d", "unit": "MW", "sample_count": len(xs), "start_date": min(values).isoformat() if values else None, "end_date": max(values).isoformat() if values else None, "mean": mean(xs) if xs else None, "median": median(xs) if xs else None, "minimum": min(xs) if xs else None, "maximum": max(xs) if xs else None}
