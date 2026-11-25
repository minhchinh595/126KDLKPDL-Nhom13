"""Add NEM time-series observations."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261125_0003"
down_revision: Union[str, None] = "20261124_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nem_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("network_code", sa.String(length=30), nullable=False),
        sa.Column("metric", sa.String(length=80), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("result", sa.String(length=120), nullable=False),
        sa.Column(
            "grouping_type",
            sa.String(length=30),
            server_default=sa.text("'network'"),
            nullable=False,
        ),
        sa.Column(
            "grouping_code",
            sa.String(length=80),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "network_code",
            "metric",
            "interval",
            "observed_at",
            "result",
            "grouping_type",
            "grouping_code",
            name="uq_nem_observations_natural_key",
        ),
    )
    op.create_index(
        "ix_nem_observations_dataset_id", "nem_observations", ["dataset_id"]
    )
    op.create_index(
        "ix_nem_observations_observed_at", "nem_observations", ["observed_at"]
    )
    op.create_index(
        "ix_nem_observations_metric_interval_time",
        "nem_observations",
        ["metric", "interval", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nem_observations_metric_interval_time", table_name="nem_observations"
    )
    op.drop_index("ix_nem_observations_observed_at", table_name="nem_observations")
    op.drop_index("ix_nem_observations_dataset_id", table_name="nem_observations")
    op.drop_table("nem_observations")
