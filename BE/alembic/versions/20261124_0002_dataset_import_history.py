"""Add dataset import history without altering existing consumption data."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261124_0002"
down_revision: Union[str, None] = "20261122_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("storage_key", sa.String(80), nullable=True))
    op.create_unique_constraint("uq_datasets_storage_key", "datasets", ["storage_key"])
    op.create_table(
        "dataset_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rows_read", sa.Integer(), server_default="0", nullable=False),
        sa.Column("inserted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_dataset_imports_dataset_id", "dataset_imports", ["dataset_id"])
    op.create_index("ix_dataset_imports_started_at", "dataset_imports", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_dataset_imports_started_at", table_name="dataset_imports")
    op.drop_index("ix_dataset_imports_dataset_id", table_name="dataset_imports")
    op.drop_table("dataset_imports")
    op.drop_constraint("uq_datasets_storage_key", "datasets", type_="unique")
    op.drop_column("datasets", "storage_key")
