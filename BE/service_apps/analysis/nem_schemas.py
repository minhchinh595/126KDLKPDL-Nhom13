from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.nem.schemas import SUPPORTED_METRICS_BY_INTERVAL


class NEMRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str = Field(min_length=1)
    interval: str = Field(min_length=1)
    observed_at: datetime
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)
    result: str = Field(min_length=1)
    grouping_type: str = "network"
    grouping_code: str = ""

    @field_validator("observed_at")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value

    @field_validator("interval")
    @classmethod
    def supported_interval(cls, value: str) -> str:
        if value not in SUPPORTED_METRICS_BY_INTERVAL:
            raise ValueError("interval is unsupported")
        return value

    @field_validator("grouping_type")
    @classmethod
    def network_only(cls, value: str) -> str:
        if value != "network":
            raise ValueError("only network-level observations are supported")
        return value

    @field_validator("grouping_code")
    @classmethod
    def no_region_code(cls, value: str) -> str:
        if value:
            raise ValueError("network-level grouping_code must be empty")
        return value

    @model_validator(mode="after")
    def validate_metric_interval(self):
        if self.metric not in SUPPORTED_METRICS_BY_INTERVAL.get(self.interval, ()):
            raise ValueError("metric and interval combination is unsupported")
        return self


class NEMRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[NEMRecord]


class NEMTrendRequest(NEMRecordsRequest):
    view: Literal["day", "week", "month"] = "day"
    metric: Literal["demand", "price", "demand_energy", "generation_renewable", "renewable_proportion"] = "demand"


class NEMDistributionRequest(NEMRecordsRequest):
    metric: Literal["demand", "price", "demand_energy", "generation_renewable", "renewable_proportion"]
    interval: Literal["1d", "5m"]
    bins: int = Field(default=10, ge=2, le=50)

    @model_validator(mode="after")
    def validate_metric_interval(self):
        if self.metric not in SUPPORTED_METRICS_BY_INTERVAL.get(self.interval, ()):
            raise ValueError("metric and interval combination is unsupported")
        return self


class NEMScatterRequest(NEMRecordsRequest):
    x_metric: Literal["demand", "price", "demand_energy", "generation_renewable", "renewable_proportion"]
    y_metric: Literal["demand", "price", "demand_energy", "generation_renewable", "renewable_proportion"]
