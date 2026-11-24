from pydantic import BaseModel, ConfigDict, Field, model_validator


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
