from datetime import date
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE


NEM_FEATURES = {
    "A": ("demand", "generation_renewable", "price"),
    "B": ("demand", "generation_renewable", "price", "renewable_proportion"),
}


class MonthlyDemandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str = Field(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")
    value: float = Field(ge=0, allow_inf_nan=False)


class ClusteringRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MonthlyDemandRecord]

    @model_validator(mode="after")
    def validate_unique_months(self):
        months = [record.month for record in self.records]
        if len(months) != len(set(months)):
            raise ValueError("records must not contain duplicate months")
        return self


class ClusteringTrainRequest(ClusteringRunRequest):
    max_k: int = Field(default=5, ge=2, le=8)


class NEMDailyFeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    features: dict[str, float]


class NEMFeatureConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_names: list[str]
    feature_units: dict[str, str]
    records: list[NEMDailyFeatureRecord]
    observation_count: int = Field(ge=0)
    start_date: date | None
    end_date: date | None
    dropped_date_count: int = Field(ge=0)
    dropped_reasons: dict[str, int]
    data_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    metric_quality: dict[str, dict[str, Any]]

    @model_validator(mode="after")
    def validate_records(self):
        if len(self.feature_names) != len(set(self.feature_names)):
            raise ValueError("feature_names must be unique")
        if set(self.feature_units) != set(self.feature_names):
            raise ValueError("feature_units must match feature_names")
        if any(not unit or unit.strip() != unit for unit in self.feature_units.values()):
            raise ValueError("feature units must be non-empty and normalized as stored")
        dates = [record.date for record in self.records]
        if len(dates) != len(set(dates)):
            raise ValueError("records must not contain duplicate local dates")
        if dates != sorted(dates):
            raise ValueError("records must be ordered by local date")
        if self.observation_count != len(self.records):
            raise ValueError("observation_count must match records")
        if dates and (self.start_date != dates[0] or self.end_date != dates[-1]):
            raise ValueError("start_date and end_date must match the records")
        if not dates and (self.start_date is not None or self.end_date is not None):
            raise ValueError("empty records must not have a date range")
        for record in self.records:
            if set(record.features) != set(self.feature_names):
                raise ValueError("each record must contain exactly the configured features")
            if not all(math.isfinite(value) for value in record.features.values()):
                raise ValueError("feature values must be finite numbers")
        return self


class NEMClusteringRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: int = Field(gt=0)
    dataset_name: str
    dataset_source: str
    network_code: Literal["NEM"]
    interval: Literal["1d"]
    configurations: dict[Literal["A", "B"], NEMFeatureConfiguration]

    @model_validator(mode="after")
    def validate_identity_and_configurations(self):
        if self.dataset_name != NEM_DATASET_NAME or self.dataset_source != NEM_DATASET_SOURCE:
            raise ValueError("request must identify the configured Open Electricity NEM dataset")
        if set(self.configurations) != set(NEM_FEATURES):
            raise ValueError("configurations must contain Model A and Model B")
        for name, configuration in self.configurations.items():
            if tuple(configuration.feature_names) != NEM_FEATURES[name]:
                raise ValueError(f"Model {name} feature names or order are incompatible")
        return self


class NEMClusteringTrainRequest(NEMClusteringRequest):
    max_k: int = Field(default=5, ge=2, le=5)
