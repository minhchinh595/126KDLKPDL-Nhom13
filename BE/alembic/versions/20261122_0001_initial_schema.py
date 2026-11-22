"""Create the initial application schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261122_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), server_default="analyst", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'analyst')", name="ck_users_role"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("record_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("status", sa.String(30), server_default="ready", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", "source", name="uq_datasets_name_source"),
    )
    op.create_table(
        "model_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "model_type IN ('clustering', 'prediction', 'classification')",
            name="ck_model_runs_model_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')", name="ck_model_runs_status"
        ),
    )
    op.create_table(
        "electricity_consumption",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_id", sa.String(80), nullable=False),
        sa.Column("country", sa.String(120), nullable=False),
        sa.Column("iso3", sa.String(3), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("fuel", sa.String(80)),
        sa.Column("value", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("value >= 0", name="ck_electricity_value_nonnegative"),
    )
    op.create_index(
        "uq_electricity_natural_key",
        "electricity_consumption",
        ["country_id", "month", "metric", sa.text("(COALESCE(fuel, ''))")],
        unique=True,
    )
    op.create_index("ix_electricity_month", "electricity_consumption", ["month"])
    op.create_index(
        "ix_electricity_country_month", "electricity_consumption", ["country_id", "month"]
    )
    op.create_index(
        "ix_electricity_metric_month", "electricity_consumption", ["metric", "month"]
    )


def downgrade() -> None:
    op.drop_index("ix_electricity_metric_month", table_name="electricity_consumption")
    op.drop_index("ix_electricity_country_month", table_name="electricity_consumption")
    op.drop_index("ix_electricity_month", table_name="electricity_consumption")
    op.drop_index("uq_electricity_natural_key", table_name="electricity_consumption")
    op.drop_table("electricity_consumption")
    op.drop_table("model_runs")
    op.drop_table("datasets")
    op.drop_table("users")
