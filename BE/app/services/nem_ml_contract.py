"""Shared fixed-horizon contract for NEM daily demand models."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


NEM_BRISBANE = ZoneInfo("Australia/Brisbane")
NEM_FORECAST_HORIZON_DAYS = 2
NEM_FEATURE_SCHEMA_VERSION = "nem_daily_demand_h2_v1"
NEM_H2_ARTIFACT_NAMES = {
    "prediction": "electricity_nem_daily_demand_rf_h2.joblib",
    "classification": "electricity_nem_daily_demand_classifier_h2.joblib",
}
NEM_FEATURE_NAMES = (
    "demand_at_cutoff",
    "demand_6d_before_cutoff",
    "demand_13d_before_cutoff",
    "demand_27d_before_cutoff",
    "day_of_week",
    "day_of_year",
)
NEM_FEATURE_UNITS = {
    "demand_at_cutoff": "MW",
    "demand_6d_before_cutoff": "MW",
    "demand_13d_before_cutoff": "MW",
    "demand_27d_before_cutoff": "MW",
    "day_of_week": "weekday_index",
    "day_of_year": "day_of_year_index",
}


def nem_forecast_dates(now: datetime | date | None = None) -> tuple[date, date, date]:
    """Return Brisbane as-of, cutoff, and next-calendar-day target dates."""
    if now is None:
        as_of_date = datetime.now(NEM_BRISBANE).date()
    elif isinstance(now, datetime):
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("NEM forecast clock must be timezone-aware")
        as_of_date = now.astimezone(NEM_BRISBANE).date()
    elif isinstance(now, date):
        as_of_date = now
    else:
        raise TypeError("NEM forecast clock must be a date or timezone-aware datetime")
    cutoff_date = as_of_date - timedelta(days=1)
    forecast_date = as_of_date + timedelta(days=1)
    return as_of_date, cutoff_date, forecast_date
