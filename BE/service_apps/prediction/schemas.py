from datetime import date, datetime, timedelta
from decimal import Decimal
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE
from app.services.nem_ml_contract import (
    NEM_BRISBANE,
    NEM_FEATURE_NAMES,
    NEM_FEATURE_SCHEMA_VERSION,
    NEM_FEATURE_UNITS,
    NEM_FORECAST_HORIZON_DAYS,
)


class MonthlyDemandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str = Field(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")
    value: float = Field(ge=0, allow_inf_nan=False)


class PredictionRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MonthlyDemandRecord]

    @model_validator(mode="after")
    def validate_unique_months(self):
        months = [record.month for record in self.records]
        if len(months) != len(set(months)):
            raise ValueError("records must not contain duplicate months")
        return self


class NEMDemandObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    value: Decimal = Field(ge=0, allow_inf_nan=False)
    unit: Literal["MW"]
    result: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timezone(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if not self.value.is_finite():
            raise ValueError("demand values must be finite")
        return self


class NEMSupervisedSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff_date: date
    target_date: date
    features: dict[str, float]
    target: float = Field(ge=0, allow_inf_nan=False)


class NEMForecastFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    cutoff_date: date
    forecast_date: date
    last_observed_date: date
    last_observed_at: datetime
    feature_names: list[str]
    features: dict[str, float]


class NEMPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: int = Field(gt=0)
    dataset_name: str
    dataset_source: str
    network_code: Literal["NEM"]
    metric: Literal["demand"]
    interval: Literal["1d"]
    unit: Literal["MW"]
    feature_names: list[str]
    feature_units: dict[str, str]
    observations: list[NEMDemandObservation]
    observation_count: int = Field(ge=0)
    observation_start: date | None
    observation_end: date | None
    missing_dates: list[date]
    duplicate_timestamps: list[str]
    excluded_sample_count: int = Field(ge=0)
    exclusion_reasons: dict[str, int]
    training_samples: list[NEMSupervisedSample]
    training_sample_count: int = Field(ge=0)
    training_start: date | None
    training_end: date | None
    as_of_date: date
    cutoff_date: date
    forecast_date: date
    last_observed_date: date | None
    forecast_status: Literal["ready", "not_ready"]
    forecast_message: str | None
    forecast: NEMForecastFeatures | None
    data_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_contract(self):
        if self.dataset_name != NEM_DATASET_NAME or self.dataset_source != NEM_DATASET_SOURCE:
            raise ValueError("request must identify the configured Open Electricity NEM dataset")
        if self.feature_names != list(NEM_FEATURE_NAMES):
            raise ValueError("NEM prediction feature names or order are incompatible")
        if self.feature_units != NEM_FEATURE_UNITS:
            raise ValueError("NEM prediction feature units are incompatible")
        if self.horizon_days != NEM_FORECAST_HORIZON_DAYS:
            raise ValueError("NEM prediction horizon is incompatible")
        if self.feature_schema_version != NEM_FEATURE_SCHEMA_VERSION:
            raise ValueError("NEM prediction feature schema is incompatible")
        if self.observation_count != len(self.observations):
            raise ValueError("observation_count must match observations")
        local_dates = [row.observed_at.astimezone(NEM_BRISBANE).date() for row in self.observations]
        if local_dates != sorted(local_dates) or len(local_dates) != len(set(local_dates)):
            raise ValueError("observations must be ordered and unique by Brisbane local date")
        if any(local_day > self.cutoff_date for local_day in local_dates):
            raise ValueError("observations must not include dates after cutoff_date in Brisbane time")
        if local_dates:
            if local_dates[0] != self.observation_start or local_dates[-1] != self.observation_end:
                raise ValueError("observation date range must match the observations")
        elif self.observation_start is not None or self.observation_end is not None or self.forecast_status != "not_ready":
            raise ValueError("empty observations are allowed only for a not_ready forecast")
        sample_dates = [sample.target_date for sample in self.training_samples]
        if sample_dates != sorted(sample_dates) or len(sample_dates) != len(set(sample_dates)):
            raise ValueError("training samples must be ordered and unique by target date")
        if self.training_sample_count != len(self.training_samples):
            raise ValueError("training_sample_count must match training_samples")
        if sample_dates and (self.training_start != sample_dates[0] or self.training_end != sample_dates[-1]):
            raise ValueError("training date range must match the supervised samples")
        if not sample_dates and (self.training_start is not None or self.training_end is not None):
            raise ValueError("empty training samples must not have a date range")
        for sample in self.training_samples:
            if sample.target_date != sample.cutoff_date + timedelta(days=NEM_FORECAST_HORIZON_DAYS):
                raise ValueError("training target_date must be two days after cutoff_date")
            if sample.target_date > self.cutoff_date:
                raise ValueError("training samples must not include targets after the complete-data cutoff")
            if set(sample.features) != set(NEM_FEATURE_NAMES):
                raise ValueError("each supervised sample must contain the configured features")
            if not all(math.isfinite(value) for value in sample.features.values()):
                raise ValueError("supervised feature values must be finite")
        if self.cutoff_date != self.as_of_date - timedelta(days=1):
            raise ValueError("cutoff_date must be the day before as_of_date in Brisbane time")
        if self.forecast_date != self.as_of_date + timedelta(days=1):
            raise ValueError("forecast_date must be tomorrow in Brisbane time")
        if self.forecast_date != self.cutoff_date + timedelta(days=NEM_FORECAST_HORIZON_DAYS):
            raise ValueError("forecast_date must be two days after cutoff_date")
        if self.forecast_status == "ready":
            if self.forecast is None or self.forecast_message is not None:
                raise ValueError("ready forecast must contain features and no not-ready message")
            if self.last_observed_date != self.cutoff_date:
                raise ValueError("latest complete observation must cover cutoff_date")
            if self.forecast.as_of_date != self.as_of_date or self.forecast.cutoff_date != self.cutoff_date:
                raise ValueError("forecast date context does not match request")
            if self.forecast.forecast_date != self.forecast_date:
                raise ValueError("forecast_date does not match request context")
            if self.forecast.last_observed_date != self.cutoff_date:
                raise ValueError("forecast last observation must match cutoff_date")
            if self.forecast.last_observed_at.tzinfo is None or self.forecast.last_observed_at.utcoffset() is None:
                raise ValueError("last_observed_at must include a timezone")
            if self.forecast.last_observed_at.astimezone(NEM_BRISBANE).date() != self.cutoff_date:
                raise ValueError("last_observed_at must match cutoff_date in Brisbane time")
            if self.forecast.feature_names != list(NEM_FEATURE_NAMES):
                raise ValueError("forecast feature names or order are incompatible")
            if set(self.forecast.features) != set(NEM_FEATURE_NAMES):
                raise ValueError("forecast features must contain the configured feature names")
            if not all(math.isfinite(value) for value in self.forecast.features.values()):
                raise ValueError("forecast feature values must be finite")
        elif self.forecast is not None or not self.forecast_message:
            raise ValueError("not_ready request must omit forecast features and explain why")
        return self
    horizon_days: Literal[2]
    feature_schema_version: Literal["nem_daily_demand_h2_v1"]
