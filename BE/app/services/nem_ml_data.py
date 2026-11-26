"""Shared, provenance-aware daily NEM data loading for ML preparation.

This module only reads observations and builds in-memory supervised samples. It
does not impute gaps, remove outliers, train models, or write to the database.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NEMObservation
from app.nem.schemas import SUPPORTED_METRICS_BY_INTERVAL
from app.services.nem_data import BRISBANE, resolve_nem_dataset
from app.services.nem_ml_contract import (
    NEM_FEATURE_NAMES,
    NEM_FEATURE_SCHEMA_VERSION,
    NEM_FEATURE_UNITS,
    NEM_FORECAST_HORIZON_DAYS,
    nem_forecast_dates,
)


NEM_CLUSTERING_FEATURE_CONFIGS = {
    "A": ("demand", "generation_renewable", "price"),
    "B": ("demand", "generation_renewable", "price", "renewable_proportion"),
}

NEM_EXPECTED_DAILY_UNITS = {
    "demand": "MW",
    "generation_renewable": "MW",
    "price": "$/MWh",
    "renewable_proportion": "%",
    "demand_energy": "MWh",
}
_NON_NEGATIVE_METRICS = {"demand", "generation_renewable", "demand_energy"}


class NEMMLDataError(ValueError):
    """NEM data cannot safely be represented for the requested ML task."""


class NEMForecastNotReady(NEMMLDataError):
    """The daily data does not yet support the requested calendar forecast."""

    def __init__(self, message: str, *, as_of_date: date, cutoff_date: date, forecast_date: date, last_observed_date: date | None):
        super().__init__(message)
        self.as_of_date = as_of_date
        self.cutoff_date = cutoff_date
        self.forecast_date = forecast_date
        self.last_observed_date = last_observed_date


@dataclass(frozen=True, slots=True)
class DailyObservation:
    observed_at: datetime | None
    value: Decimal | None
    unit: str
    result: str

    @property
    def local_date(self) -> date:
        if (
            self.observed_at is None
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise NEMMLDataError("observation timestamp must be timezone-aware")
        return self.observed_at.astimezone(BRISBANE).date()


@dataclass(frozen=True, slots=True)
class NEMDailyMLData:
    dataset_id: int
    dataset_name: str
    dataset_source: str
    network_code: str
    metric: str
    interval: str
    unit: str
    observations: tuple[DailyObservation, ...]
    start_date: date | None
    end_date: date | None
    missing_dates: tuple[date, ...]
    duplicate_timestamps: tuple[str, ...]
    duplicate_local_dates: tuple[str, ...]
    unit_mismatch_count: int
    null_timestamp_count: int
    timezone_naive_count: int
    null_value_count: int
    invalid_value_count: int
    non_finite_value_count: int
    zero_count: int
    negative_count: int
    data_fingerprint: str

    @property
    def observation_count(self) -> int:
        return len(self.observations)

    def provenance(self, feature_names: Sequence[str] = ()) -> dict[str, Any]:
        """Return JSONB-compatible provenance fields for a future ModelRun."""
        return {
            "dataset_name": self.dataset_name,
            "dataset_source": self.dataset_source,
            "dataset_id": self.dataset_id,
            "network_code": self.network_code,
            "metric": self.metric,
            "interval": self.interval,
            "unit": self.unit,
            "training_start": self.start_date.isoformat() if self.start_date else None,
            "training_end": self.end_date.isoformat() if self.end_date else None,
            "observation_count": self.observation_count,
            "feature_names": list(feature_names),
            "data_fingerprint": self.data_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class DailySupervisedSamples:
    feature_names: tuple[str, ...]
    features: tuple[dict[str, float], ...]
    cutoff_dates: tuple[date, ...]
    target: tuple[float, ...]
    target_timestamps: tuple[datetime, ...]
    target_name: str
    target_unit: str
    valid_sample_count: int
    excluded_sample_count: int
    exclusion_reasons: dict[str, int]
    valid_samples_by_lag: dict[str, int]
    data_fingerprint: str


@dataclass(frozen=True, slots=True)
class NEMClusteringInput:
    dataset_id: int
    dataset_name: str
    dataset_source: str
    configurations: dict[str, dict[str, Any]]

    def as_service_payload(self) -> dict[str, Any]:
        """Build the internal service request without database-only values."""
        return {
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "dataset_source": self.dataset_source,
            "network_code": "NEM",
            "interval": "1d",
            "configurations": self.configurations,
        }


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed


def _validate_metric_domain(metric: str, value: float, observed_day: date | None) -> None:
    day_label = f" on {observed_day.isoformat()}" if observed_day is not None else " with missing timestamp"
    if metric in _NON_NEGATIVE_METRICS and value < 0:
        raise NEMMLDataError(
            f"daily NEM metric {metric!r} has a negative value{day_label}"
        )
    if metric == "renewable_proportion" and not 0 <= value <= 100:
        raise NEMMLDataError(
            f"daily NEM metric 'renewable_proportion' must be within [0, 100] percent; "
            f"invalid value{day_label}"
        )


def _fingerprint(
    *, dataset_id: int, dataset_name: str, dataset_source: str,
    network_code: str, metric: str, interval: str, unit: str,
    rows: Sequence[DailyObservation],
) -> str:
    payload = {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "dataset_source": dataset_source,
        "network_code": network_code,
        "metric": metric,
        "interval": interval,
        "unit": unit,
        "observations": [
            {
                "observed_at": row.observed_at.isoformat() if row.observed_at else None,
                "value": str(row.value) if row.value is not None else None,
                "unit": row.unit,
                "result": row.result,
            }
            for row in rows
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_nem_daily_metric(db: Session, *, metric: str, unit: str) -> NEMDailyMLData:
    """Load an explicitly unit-verified daily network-level NEM metric.

    ``unit`` is mandatory so new metrics are only consumed after their units
    have been independently verified. No VNM fallback or implicit conversion
    is performed.
    """
    if not isinstance(metric, str) or not metric.strip():
        raise NEMMLDataError("metric must be a non-empty string")
    if not isinstance(unit, str) or not unit.strip():
        raise NEMMLDataError("unit must be explicitly specified and verified")
    if metric not in SUPPORTED_METRICS_BY_INTERVAL["1d"]:
        raise NEMMLDataError("metric is not a supported daily NEM metric")
    expected_unit = NEM_EXPECTED_DAILY_UNITS.get(metric)
    if expected_unit is None:
        raise NEMMLDataError(f"daily NEM metric {metric!r} has no verified unit contract")
    if unit != expected_unit:
        raise NEMMLDataError(
            f"daily NEM metric {metric!r} requires unit {expected_unit!r}, got {unit!r}"
        )

    dataset = resolve_nem_dataset(db)
    statement = select(NEMObservation).where(
        NEMObservation.dataset_id == dataset.id,
        NEMObservation.network_code == "NEM",
        NEMObservation.metric == metric,
        NEMObservation.interval == "1d",
        NEMObservation.grouping_type == "network",
        NEMObservation.grouping_code == "",
    ).order_by(NEMObservation.observed_at, NEMObservation.result, NEMObservation.id)
    candidates = db.scalars(statement).all()

    mismatched_units = sorted({row.unit for row in candidates if row.unit != expected_unit}, key=str)
    if mismatched_units:
        raise NEMMLDataError(
            f"daily NEM metric {metric!r} requires unit {expected_unit!r}; "
            f"found incompatible unit label(s): {', '.join(map(str, mismatched_units))}"
        )
    unit_mismatch_count = 0
    selected = candidates
    null_timestamp_count = sum(row.observed_at is None for row in selected)
    null_value_count = sum(row.value is None for row in selected)
    def sort_key(row: NEMObservation) -> tuple[int, datetime, str]:
        timestamp = row.observed_at
        if timestamp is None:
            return (1, datetime.max.replace(tzinfo=BRISBANE), row.result or "")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            # Retain invalid timestamps for quality reporting, but sort them deterministically.
            return (0, timestamp.replace(tzinfo=BRISBANE), row.result or "")
        return (0, timestamp.astimezone(BRISBANE), row.result or "")

    selected.sort(key=sort_key)
    timezone_naive_count = sum(
        row.observed_at is not None
        and (row.observed_at.tzinfo is None or row.observed_at.utcoffset() is None)
        for row in selected
    )
    invalid_value_count = sum(
        row.value is not None and _to_decimal(row.value) is None for row in selected
    )

    observations = tuple(
        DailyObservation(
            observed_at=row.observed_at,
            value=_to_decimal(row.value),
            unit=row.unit,
            result=row.result,
        )
        for row in selected
    )
    non_finite_count = sum(
        obs.value is not None and not obs.value.is_finite() for obs in observations
    )
    for obs in observations:
        if obs.value is not None and obs.value.is_finite():
            if obs.observed_at is None:
                observed_day = None
            elif obs.observed_at.tzinfo is None or obs.observed_at.utcoffset() is None:
                observed_day = obs.observed_at.date()
            else:
                observed_day = obs.local_date
            _validate_metric_domain(metric, float(obs.value), observed_day)
    zero_count = sum(obs.value == 0 for obs in observations if obs.value is not None)
    negative_count = sum(obs.value < 0 for obs in observations if obs.value is not None)

    timestamps = [
        obs.observed_at for obs in observations
        if obs.observed_at is not None
        and obs.observed_at.tzinfo is not None
        and obs.observed_at.utcoffset() is not None
    ]
    timestamp_counts = Counter(ts.astimezone(timezone.utc).isoformat() for ts in timestamps)
    duplicate_timestamps = tuple(sorted(ts for ts, count in timestamp_counts.items() if count > 1))
    local_date_counts = Counter(
        obs.local_date for obs in observations
        if obs.observed_at is not None
        and obs.observed_at.tzinfo is not None
        and obs.observed_at.utcoffset() is not None
    )
    duplicate_local_dates = tuple(
        sorted(day.isoformat() for day, count in local_date_counts.items() if count > 1)
    )
    dates = sorted(local_date_counts)
    missing_dates: list[date] = []
    if dates:
        day = dates[0]
        while day <= dates[-1]:
            if day not in local_date_counts:
                missing_dates.append(day)
            day += timedelta(days=1)

    fingerprint = _fingerprint(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        dataset_source=dataset.source,
        network_code="NEM",
        metric=metric,
        interval="1d",
        unit=unit,
        rows=observations,
    )
    return NEMDailyMLData(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        dataset_source=dataset.source,
        network_code="NEM",
        metric=metric,
        interval="1d",
        unit=unit,
        observations=observations,
        start_date=dates[0] if dates else None,
        end_date=dates[-1] if dates else None,
        missing_dates=tuple(missing_dates),
        duplicate_timestamps=duplicate_timestamps,
        duplicate_local_dates=duplicate_local_dates,
        unit_mismatch_count=unit_mismatch_count,
        null_timestamp_count=null_timestamp_count,
        timezone_naive_count=timezone_naive_count,
        null_value_count=null_value_count,
        invalid_value_count=invalid_value_count,
        non_finite_value_count=non_finite_count,
        zero_count=zero_count,
        negative_count=negative_count,
        data_fingerprint=fingerprint,
    )


def load_nem_daily_demand(db: Session) -> NEMDailyMLData:
    """Load verified network-level daily demand in MW."""
    return load_nem_daily_metric(db, metric="demand", unit="MW")


def build_daily_supervised_features(
    data: NEMDailyMLData,
    *,
    max_target_date: date | None = None,
) -> DailySupervisedSamples:
    """Build leakage-safe daily demand samples from prior observations only."""
    if data.metric != "demand" or data.interval != "1d" or data.unit != "MW":
        raise NEMMLDataError("supervised demand features require daily demand in MW")
    if data.duplicate_timestamps or data.duplicate_local_dates:
        raise NEMMLDataError("daily demand contains duplicate timestamps or local dates")
    if data.null_timestamp_count or data.timezone_naive_count:
        raise NEMMLDataError("daily demand contains missing or timezone-naive timestamps")

    by_date: dict[date, DailyObservation] = {obs.local_date: obs for obs in data.observations}

    feature_names = NEM_FEATURE_NAMES
    features: list[dict[str, float]] = []
    cutoff_dates: list[date] = []
    targets: list[float] = []
    target_timestamps: list[datetime] = []
    excluded = Counter()
    offsets = (0, 6, 13, 27)
    samples_by_lag = {name: 0 for name in NEM_FEATURE_NAMES[:4]}

    if not by_date:
        return DailySupervisedSamples(
            feature_names=feature_names,
            features=(),
            cutoff_dates=(),
            target=(),
            target_timestamps=(),
            target_name="demand",
            target_unit="MW",
            valid_sample_count=0,
            excluded_sample_count=0,
            exclusion_reasons={},
            valid_samples_by_lag=samples_by_lag,
            data_fingerprint=data.data_fingerprint,
        )

    for target_day in sorted(by_date):
        # A current forecast may have observations newer than its complete-data
        # cutoff. Never let their target labels enter model training.
        if max_target_date is not None and target_day > max_target_date:
            continue
        target_obs = by_date[target_day]
        target_value = target_obs.value
        if target_value is None or not target_value.is_finite():
            excluded["invalid_target_value"] += 1
            continue
        target_float = float(target_value)
        if not math.isfinite(target_float):
            excluded["invalid_target_value"] += 1
            continue

        cutoff_day = target_day - timedelta(days=NEM_FORECAST_HORIZON_DAYS)
        cutoff_values: list[float] = []
        missing_lags = []
        invalid_lags = []
        for name, offset in zip(NEM_FEATURE_NAMES[:4], offsets):
            lag_day = cutoff_day - timedelta(days=offset)
            lag_obs = by_date.get(lag_day)
            if lag_obs is None:
                missing_lags.append(offset)
            elif lag_obs.value is None or not lag_obs.value.is_finite():
                invalid_lags.append(offset)
            else:
                cutoff_values.append(float(lag_obs.value))
                samples_by_lag[name] += 1
        if missing_lags:
            excluded["missing_lag_observation"] += 1
            continue
        if invalid_lags:
            excluded["invalid_lag_value"] += 1
            continue

        row = dict(zip(NEM_FEATURE_NAMES[:4], cutoff_values))
        row["day_of_week"] = float(target_day.weekday())
        row["day_of_year"] = float(target_day.timetuple().tm_yday)
        if not all(math.isfinite(value) for value in row.values()):
            excluded["non_finite_feature"] += 1
            continue
        features.append(row)
        cutoff_dates.append(cutoff_day)
        targets.append(target_float)
        target_timestamps.append(
            datetime.combine(target_day, datetime.min.time(), tzinfo=BRISBANE)
        )

    return DailySupervisedSamples(
        feature_names=feature_names,
        features=tuple(features),
        cutoff_dates=tuple(cutoff_dates),
        target=tuple(targets),
        target_timestamps=tuple(target_timestamps),
        target_name="demand",
        target_unit="MW",
        valid_sample_count=len(targets),
        excluded_sample_count=sum(excluded.values()),
        exclusion_reasons=dict(excluded),
        valid_samples_by_lag=samples_by_lag,
        data_fingerprint=data.data_fingerprint,
    )


def build_next_day_demand_features(
    data: NEMDailyMLData,
    *,
    now: datetime | date | None = None,
) -> dict[str, Any]:
    """Build fixed two-day-horizon features for tomorrow in Brisbane time."""
    if data.metric != "demand" or data.interval != "1d" or data.unit != "MW":
        raise NEMMLDataError("next-day demand features require daily demand in MW")
    if data.duplicate_timestamps or data.duplicate_local_dates:
        raise NEMMLDataError("daily demand contains duplicate timestamps or local dates")
    if data.null_timestamp_count or data.timezone_naive_count:
        raise NEMMLDataError("daily demand contains missing or timezone-naive timestamps")

    as_of_date, cutoff_date, forecast_date = nem_forecast_dates(now)
    by_date = {
        observation.local_date: observation
        for observation in data.observations
        if observation.local_date <= cutoff_date
    }
    if not by_date:
        raise NEMForecastNotReady(
            "NEM daily demand has no observations",
            as_of_date=as_of_date,
            cutoff_date=cutoff_date,
            forecast_date=forecast_date,
            last_observed_date=None,
        )
    last_observed_date = max(by_date)
    if cutoff_date not in by_date:
        raise NEMForecastNotReady(
            f"NEM daily demand is not complete through cutoff date {cutoff_date.isoformat()}",
            as_of_date=as_of_date,
            cutoff_date=cutoff_date,
            forecast_date=forecast_date,
            last_observed_date=last_observed_date,
        )
    feature_values: dict[str, float] = {}
    for name, offset in zip(NEM_FEATURE_NAMES[:4], (0, 6, 13, 27)):
        lag_date = cutoff_date - timedelta(days=offset)
        observation = by_date.get(lag_date)
        if observation is None:
            raise NEMForecastNotReady(
                f"NEM daily demand feature date {lag_date.isoformat()} is missing for forecast {forecast_date.isoformat()}",
                as_of_date=as_of_date,
                cutoff_date=cutoff_date,
                forecast_date=forecast_date,
                last_observed_date=last_observed_date,
            )
        if observation.value is None or not observation.value.is_finite():
            raise NEMForecastNotReady(
                f"NEM daily demand feature date {lag_date.isoformat()} is invalid for forecast {forecast_date.isoformat()}",
                as_of_date=as_of_date,
                cutoff_date=cutoff_date,
                forecast_date=forecast_date,
                last_observed_date=last_observed_date,
            )
        value = float(observation.value)
        if not math.isfinite(value) or value < 0:
            raise NEMForecastNotReady(
                f"NEM daily demand feature date {lag_date.isoformat()} is invalid for forecast {forecast_date.isoformat()}",
                as_of_date=as_of_date,
                cutoff_date=cutoff_date,
                forecast_date=forecast_date,
                last_observed_date=last_observed_date,
            )
        feature_values[name] = value
    feature_values["day_of_week"] = float(forecast_date.weekday())
    feature_values["day_of_year"] = float(forecast_date.timetuple().tm_yday)
    feature_names = tuple(
        list(NEM_FEATURE_NAMES)
    )
    latest_observation = max(
        (observation for observation in data.observations if observation.local_date == cutoff_date),
        key=lambda observation: observation.observed_at.astimezone(BRISBANE),
    )
    return {
        "as_of_date": as_of_date.isoformat(),
        "cutoff_date": cutoff_date.isoformat(),
        "forecast_date": forecast_date.isoformat(),
        "last_observed_date": cutoff_date.isoformat(),
        "last_observed_at": latest_observation.observed_at.isoformat(),
        "feature_names": list(feature_names),
        "features": feature_values,
    }


def build_nem_prediction_payload(data: NEMDailyMLData, *, now: datetime | date | None = None) -> dict[str, Any]:
    """Serialize validated NEM demand, supervised samples and next-day inputs."""
    if data.unit_mismatch_count:
        raise NEMMLDataError("NEM daily demand contains observations with a unit other than MW")
    if data.null_value_count or data.invalid_value_count or data.non_finite_value_count:
        raise NEMMLDataError("NEM daily demand contains null or invalid values")
    if data.negative_count:
        raise NEMMLDataError("NEM daily demand contains negative values")
    as_of_date, cutoff_date, forecast_date = nem_forecast_dates(now)
    supervised = build_daily_supervised_features(data, max_target_date=cutoff_date)
    eligible_observations = tuple(
        observation
        for observation in data.observations
        if observation.observed_at is not None
        and observation.observed_at.tzinfo is not None
        and observation.observed_at.utcoffset() is not None
        and observation.local_date <= cutoff_date
    )
    eligible_dates = [observation.local_date for observation in eligible_observations]
    observation_start = min(eligible_dates) if eligible_dates else None
    observation_end = max(eligible_dates) if eligible_dates else None
    cutoff_missing_dates = [day for day in data.missing_dates if day <= cutoff_date]
    forecast_input_fingerprint = _fingerprint(
        dataset_id=data.dataset_id,
        dataset_name=data.dataset_name,
        dataset_source=data.dataset_source,
        network_code=data.network_code,
        metric=data.metric,
        interval=data.interval,
        unit=data.unit,
        rows=eligible_observations,
    )
    last_observed_date = max(eligible_dates) if eligible_dates else None
    try:
        next_day = build_next_day_demand_features(data, now=as_of_date)
        forecast_message = None
    except NEMForecastNotReady as exc:
        # Training is still valid with historical samples when a current
        # calendar forecast cannot be formed. Gateway Run checks this field.
        next_day = None
        forecast_message = str(exc)
    observations = []
    for observation in eligible_observations:
        if observation.observed_at is None or observation.value is None:
            raise NEMMLDataError("NEM demand observations contain missing fields")
        observations.append({
            "observed_at": observation.observed_at.isoformat(),
            "value": str(observation.value),
            "unit": observation.unit,
            "result": observation.result,
        })
    return {
        "dataset_id": data.dataset_id,
        "dataset_name": data.dataset_name,
        "dataset_source": data.dataset_source,
        "network_code": data.network_code,
        "metric": data.metric,
        "interval": data.interval,
        "unit": data.unit,
        "horizon_days": NEM_FORECAST_HORIZON_DAYS,
        "feature_schema_version": NEM_FEATURE_SCHEMA_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "cutoff_date": cutoff_date.isoformat(),
        "forecast_date": forecast_date.isoformat(),
        "last_observed_date": last_observed_date.isoformat() if last_observed_date else None,
        "forecast_message": forecast_message,
        "feature_names": list(supervised.feature_names),
        "feature_units": NEM_FEATURE_UNITS.copy(),
        "observations": observations,
        "observation_count": len(eligible_observations),
        "observation_start": observation_start.isoformat() if observation_start else None,
        "observation_end": observation_end.isoformat() if observation_end else None,
        "missing_dates": [day.isoformat() for day in cutoff_missing_dates],
        "duplicate_timestamps": list(data.duplicate_timestamps),
        "excluded_sample_count": supervised.excluded_sample_count,
        "exclusion_reasons": supervised.exclusion_reasons,
        "training_samples": [
            {
                "cutoff_date": cutoff_date.isoformat(),
                "target_date": timestamp.date().isoformat(),
                "features": features,
                "target": target,
            }
            for cutoff_date, timestamp, features, target in zip(
                supervised.cutoff_dates, supervised.target_timestamps, supervised.features, supervised.target
            )
        ],
        "training_sample_count": supervised.valid_sample_count,
        "training_start": supervised.target_timestamps[0].date().isoformat() if supervised.target_timestamps else None,
        "training_end": supervised.target_timestamps[-1].date().isoformat() if supervised.target_timestamps else None,
        "forecast": next_day,
        "forecast_status": "ready" if next_day is not None else "not_ready",
        "data_fingerprint": forecast_input_fingerprint,
    }


def _linear_quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def load_nem_clustering_input(db: Session) -> NEMClusteringInput:
    """Load and align verified daily network-level features for Model A and B.

    Values and unit labels are preserved exactly as stored. Rows are never
    imputed or removed as outliers; unusable dates are reported per feature set.
    """
    dataset = resolve_nem_dataset(db)
    metrics = tuple(dict.fromkeys(
        metric
        for feature_names in NEM_CLUSTERING_FEATURE_CONFIGS.values()
        for metric in feature_names
    ))
    statement = select(NEMObservation).where(
        NEMObservation.dataset_id == dataset.id,
        NEMObservation.network_code == "NEM",
        NEMObservation.metric.in_(metrics),
        NEMObservation.interval == "1d",
        NEMObservation.grouping_type == "network",
        NEMObservation.grouping_code == "",
    ).order_by(NEMObservation.metric, NEMObservation.observed_at, NEMObservation.result, NEMObservation.id)
    rows = db.scalars(statement).all()

    grouped: dict[str, list[NEMObservation]] = {metric: [] for metric in metrics}
    for row in rows:
        grouped[row.metric].append(row)

    values_by_metric: dict[str, dict[date, float]] = {}
    units_by_metric: dict[str, str] = {}
    invalid_dates_by_metric: dict[str, dict[date, str]] = {}
    quality: dict[str, dict[str, Any]] = {}

    for metric in metrics:
        metric_rows = grouped[metric]
        if not metric_rows:
            raise NEMMLDataError(f"required daily NEM metric {metric!r} has no observations")

        units = {row.unit for row in metric_rows}
        if len(units) != 1:
            raise NEMMLDataError(f"metric {metric!r} contains inconsistent unit labels")
        unit = next(iter(units))
        expected_unit = NEM_EXPECTED_DAILY_UNITS.get(metric)
        if expected_unit is None:
            raise NEMMLDataError(f"daily NEM metric {metric!r} has no verified unit contract")
        if unit != expected_unit:
            raise NEMMLDataError(
                f"daily NEM metric {metric!r} requires unit {expected_unit!r}, got {unit!r}"
            )
        units_by_metric[metric] = unit
        by_date: dict[date, list[NEMObservation]] = {}
        invalid_dates: dict[date, str] = {}
        for row in metric_rows:
            if row.observed_at is None or row.observed_at.tzinfo is None or row.observed_at.utcoffset() is None:
                raise NEMMLDataError(f"metric {metric!r} contains a missing or timezone-naive timestamp")
            local_day = row.observed_at.astimezone(BRISBANE).date()
            by_date.setdefault(local_day, []).append(row)
        metric_values: dict[date, float] = {}
        parsed_values: list[tuple[date, float]] = []
        null_count = 0
        invalid_count = 0
        zero_count = 0
        negative_count = 0
        for day, day_rows in by_date.items():
            if len(day_rows) != 1:
                invalid_dates[day] = "duplicate_local_date"
                continue
            raw = day_rows[0].value
            if raw is None:
                null_count += 1
                invalid_dates[day] = "null_value"
                continue
            parsed = _to_decimal(raw)
            if parsed is None or not parsed.is_finite():
                invalid_count += 1
                invalid_dates[day] = "invalid_or_non_finite_value"
                continue
            value = float(parsed)
            if not math.isfinite(value):
                invalid_count += 1
                invalid_dates[day] = "invalid_or_non_finite_value"
                continue
            _validate_metric_domain(metric, value, day)
            metric_values[day] = value
            parsed_values.append((day, value))
            zero_count += value == 0
            negative_count += value < 0

        numbers = [value for _, value in parsed_values]
        q1 = _linear_quantile(numbers, 0.25)
        q3 = _linear_quantile(numbers, 0.75)
        iqr = (q3 - q1) if q1 is not None and q3 is not None else 0
        outlier_dates = [
            day.isoformat() for day, value in parsed_values
            if q1 is not None and q3 is not None
            and (value < q1 - 1.5 * iqr or value > q3 + 1.5 * iqr)
        ]
        all_days = sorted(by_date)
        missing_dates: list[str] = []
        if all_days:
            day = all_days[0]
            while day <= all_days[-1]:
                if day not in by_date:
                    missing_dates.append(day.isoformat())
                day += timedelta(days=1)
        values_by_metric[metric] = metric_values
        invalid_dates_by_metric[metric] = invalid_dates
        quality[metric] = {
            "observation_count": len(metric_rows),
            "unit": unit,
            "start_date": min(all_days).isoformat() if all_days else None,
            "end_date": max(all_days).isoformat() if all_days else None,
            "missing_dates": missing_dates,
            "duplicate_local_dates": sum(len(day_rows) > 1 for day_rows in by_date.values()),
            "null_value_count": null_count,
            "invalid_value_count": invalid_count,
            "zero_count": zero_count,
            "negative_count": negative_count,
            "min": min(numbers) if numbers else None,
            "q1": q1,
            "median": _linear_quantile(numbers, 0.5),
            "q3": q3,
            "max": max(numbers) if numbers else None,
            "iqr_outlier_count": len(outlier_dates),
            "iqr_outlier_dates": outlier_dates,
        }

    configurations: dict[str, dict[str, Any]] = {}
    for configuration_name, feature_names in NEM_CLUSTERING_FEATURE_CONFIGS.items():
        observed_date_union = set().union(*(
            set(values_by_metric[name]) | set(invalid_dates_by_metric[name])
            for name in feature_names
        ))
        date_union: set[date] = set()
        if observed_date_union:
            day = min(observed_date_union)
            while day <= max(observed_date_union):
                date_union.add(day)
                day += timedelta(days=1)
        aligned_records: list[dict[str, Any]] = []
        dropped_reasons: Counter[str] = Counter()
        for day in sorted(date_union):
            feature_values: dict[str, float] = {}
            reasons = []
            for name in feature_names:
                if day in invalid_dates_by_metric[name]:
                    reasons.append(f"{invalid_dates_by_metric[name][day]}:{name}")
                elif day not in values_by_metric[name]:
                    reasons.append(f"missing:{name}")
                else:
                    feature_values[name] = values_by_metric[name][day]
            if reasons:
                dropped_reasons.update(reasons)
                continue
            aligned_records.append({"date": day.isoformat(), "features": feature_values})

        fingerprint_input = {
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "dataset_source": dataset.source,
            "network_code": "NEM",
            "interval": "1d",
            "feature_names": list(feature_names),
            "feature_units": {name: units_by_metric[name] for name in feature_names},
            "records": aligned_records,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        configurations[configuration_name] = {
            "feature_names": list(feature_names),
            "feature_units": {name: units_by_metric[name] for name in feature_names},
            "records": aligned_records,
            "observation_count": len(aligned_records),
            "start_date": aligned_records[0]["date"] if aligned_records else None,
            "end_date": aligned_records[-1]["date"] if aligned_records else None,
            "dropped_date_count": len(date_union) - len(aligned_records),
            "dropped_reasons": dict(dropped_reasons),
            "data_fingerprint": fingerprint,
            "metric_quality": {name: quality[name] for name in feature_names},
        }

    return NEMClusteringInput(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        dataset_source=dataset.source,
        configurations=configurations,
    )
