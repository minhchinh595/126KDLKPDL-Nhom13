from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Dataset, DatasetImport, ElectricityConsumption


def import_dataset_file(
    db: Session,
    dataset: Dataset,
    file_path: Path,
    mode: str,
    *,
    normalized_rows: list[dict],
) -> DatasetImport:
    history = DatasetImport(dataset_id=dataset.id, mode=mode, status="running")
    db.add(history)
    db.commit()
    db.refresh(history)
    try:
        # CSV parsing is delegated to Ingestion Service before this DB transaction.
        rows = normalized_rows
        keys = [(row["country_id"], row["month"], row["metric"], row["fuel"] or "") for row in rows]
        existing_rows = db.execute(
            select(ElectricityConsumption).where(
                ElectricityConsumption.iso3 == "VNM",
                ElectricityConsumption.metric == "demand",
                ElectricityConsumption.month.in_([row["month"] for row in rows]),
            )
        ).scalars().all()
        existing_by_key = {
            (row.country_id, row.month, row.metric, row.fuel or ""): row
            for row in existing_rows
        }
        inserted_count = updated_count = skipped_count = 0
        for row, key in zip(rows, keys):
            old = existing_by_key.get(key)
            if old is None:
                inserted_count += 1
            elif any(getattr(old, field) != value for field, value in row.items()) or old.dataset_id != dataset.id:
                updated_count += 1
            else:
                skipped_count += 1

        statement = insert(ElectricityConsumption).values(
            [{**row, "dataset_id": dataset.id} for row in rows]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                ElectricityConsumption.country_id,
                ElectricityConsumption.month,
                ElectricityConsumption.metric,
                func.coalesce(ElectricityConsumption.fuel, literal_column("''")),
            ],
            set_={
                "dataset_id": statement.excluded.dataset_id,
                "country": statement.excluded.country,
                "iso3": statement.excluded.iso3,
                "fuel": statement.excluded.fuel,
                "value": statement.excluded.value,
                "unit": statement.excluded.unit,
            },
            where=or_(
                ElectricityConsumption.dataset_id.is_distinct_from(statement.excluded.dataset_id),
                ElectricityConsumption.country.is_distinct_from(statement.excluded.country),
                ElectricityConsumption.iso3.is_distinct_from(statement.excluded.iso3),
                ElectricityConsumption.value.is_distinct_from(statement.excluded.value),
                ElectricityConsumption.unit.is_distinct_from(statement.excluded.unit),
            ),
        ).returning(ElectricityConsumption.id)
        db.execute(statement)
        dataset.record_count = len(rows)
        dataset.start_date = min(row["month"] for row in rows)
        dataset.end_date = max(row["month"] for row in rows)
        dataset.status = "imported"
        history.status = "completed"
        history.rows_read = len(rows)
        history.inserted_count = inserted_count
        history.updated_count = updated_count
        history.skipped_count = skipped_count
        history.error_count = 0
        history.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(history)
        return history
    except Exception as exc:
        db.rollback()
        failed = db.get(DatasetImport, history.id)
        failed.status = "failed"
        failed.error_count = 1
        failed.error_message = str(exc)[:2000]
        failed.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
