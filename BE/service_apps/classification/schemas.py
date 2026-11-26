from pydantic import BaseModel, ConfigDict, Field, model_validator

# Prediction and Classification consume the same normalized daily NEM demand
# payload. The shared schema prevents the services from drifting on features.
from service_apps.prediction.schemas import NEMPredictionRequest as _NEMDailyDemandRequest


class NEMClassificationRequest(_NEMDailyDemandRequest):
    """Shared validated daily demand payload for the NEM classification API."""


class MonthlyDemandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str = Field(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")
    value: float = Field(ge=0, allow_inf_nan=False)


class ClassificationRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MonthlyDemandRecord]

    @model_validator(mode="after")
    def validate_unique_months(self):
        months = [record.month for record in self.records]
        if len(months) != len(set(months)):
            raise ValueError("records must not contain duplicate months")
        return self
