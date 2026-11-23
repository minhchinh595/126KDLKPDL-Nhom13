from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: Literal["admin", "analyst"]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "analyst"] = "analyst"

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("A valid email address is required")
        return value


class UserPatch(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=80)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    role: Literal["admin", "analyst"] | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().lower()
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("A valid email address is required")
        return value


class UserStatusPatch(BaseModel):
    is_active: bool


class UserListResponse(BaseModel):
    items: list[UserPublic]
    page: int
    page_size: int
    total: int
    pages: int
