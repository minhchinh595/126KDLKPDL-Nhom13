from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NormalizedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_id: str = Field(min_length=1)
    country: str = Field(min_length=1)
    iso3: Literal["VNM"]
    month: date
    metric: Literal["demand"]
    fuel: None
    value: Decimal = Field(ge=0, allow_inf_nan=False)
    unit: Literal["TWh"]

    @field_validator("month")
    @classmethod
    def month_must_be_first_day(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("month must be the first day of a month")
        return value


class NormalizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[NormalizedRecord] = Field(min_length=1)
    rows_read: int = Field(ge=1)
    start_month: date
    end_month: date

    @model_validator(mode="after")
    def metadata_matches_rows(self):
        months = [row.month for row in self.rows]
        if self.rows_read != len(self.rows):
            raise ValueError("rows_read must match the number of rows")
        if self.start_month != min(months) or self.end_month != max(months):
            raise ValueError("month range must match rows")
        return self
