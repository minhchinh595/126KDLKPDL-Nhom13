"""ORM models for account, dataset, consumption, and model-run metadata."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'analyst')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="analyst", server_default="analyst")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("name", "source", name="uq_datasets_name_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    record_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ready", server_default="ready")

    consumption_records: Mapped[list["ElectricityConsumption"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    import_history: Mapped[list["DatasetImport"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    nem_observations: Mapped[list["NEMObservation"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DatasetImport(Base):
    __tablename__ = "dataset_imports"
    __table_args__ = (
        Index("ix_dataset_imports_dataset_id", "dataset_id"),
        Index("ix_dataset_imports_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rows_read: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    inserted_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    updated_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset] = relationship(back_populates="import_history")


class ElectricityConsumption(Base):
    __tablename__ = "electricity_consumption"
    __table_args__ = (
        Index(
            "uq_electricity_natural_key",
            "country_id",
            "month",
            "metric",
            func.coalesce(literal_column("fuel"), literal_column("''")),
            unique=True,
        ),
        Index("ix_electricity_month", "month"),
        Index("ix_electricity_country_month", "country_id", "month"),
        Index("ix_electricity_metric_month", "metric", "month"),
        CheckConstraint("value >= 0", name="ck_electricity_value_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    country_id: Mapped[str] = mapped_column(String(80), nullable=False)
    country: Mapped[str] = mapped_column(String(120), nullable=False)
    iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    fuel: Mapped[str | None] = mapped_column(String(80))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="consumption_records")


class NEMObservation(Base):
    __tablename__ = "nem_observations"
    __table_args__ = (
        UniqueConstraint(
            "network_code",
            "metric",
            "interval",
            "observed_at",
            "result",
            "grouping_type",
            "grouping_code",
            name="uq_nem_observations_natural_key",
        ),
        Index("ix_nem_observations_dataset_id", "dataset_id"),
        Index("ix_nem_observations_observed_at", "observed_at"),
        Index(
            "ix_nem_observations_metric_interval_time",
            "metric",
            "interval",
            "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    network_code: Mapped[str] = mapped_column(String(30), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[str] = mapped_column(String(120), nullable=False)
    grouping_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="network", server_default="network"
    )
    grouping_code: Mapped[str] = mapped_column(
        String(80), nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="nem_observations")


class ModelRun(Base):
    __tablename__ = "model_runs"
    __table_args__ = (
        CheckConstraint(
            "model_type IN ('clustering', 'prediction', 'classification')",
            name="ck_model_runs_model_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_model_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
