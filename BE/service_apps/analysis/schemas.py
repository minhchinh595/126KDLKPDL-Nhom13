from pydantic import BaseModel, ConfigDict, Field, model_validator


class MonthlyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str = Field(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")
    value: float = Field(ge=0, allow_inf_nan=False)


class AnalysisRecordsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MonthlyRecord]

    @model_validator(mode="after")
    def validate_unique_months(self):
        months = [record.month for record in self.records]
        if len(months) != len(set(months)):
            raise ValueError("records must not contain duplicate months")
        return self


class TrendRequest(AnalysisRecordsRequest):
    window_months: int = Field(default=12, ge=2, le=36)


class DistributionRequest(AnalysisRecordsRequest):
    bins: int = Field(default=10, ge=2, le=50)
