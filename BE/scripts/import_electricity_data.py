"""Validate and idempotently import the processed monthly electricity CSV."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import get_session_factory  # noqa: E402
from app.db.models import Dataset, ElectricityConsumption  # noqa: E402
from app.ingestion.reader import parse_csv_bytes  # noqa: E402

DATASET_NAME = "Vietnam monthly electricity demand"
DATASET_SOURCE = "Ember Monthly Electricity Data"


def load_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"CSV file not found: {path}")
    return parse_csv_bytes(path.read_bytes())


def import_rows(rows: list[dict], csv_path: Path) -> tuple[int, int]:
    session_factory = get_session_factory()
    inserted = 0
    with session_factory() as session, session.begin():
        dataset_stmt = (
            insert(Dataset)
            .values(
                name=DATASET_NAME,
                source=DATASET_SOURCE,
                file_name=csv_path.name,
                description="Processed monthly national electricity demand for Vietnam (TWh).",
                record_count=0,
                status="ready",
            )
            .on_conflict_do_update(
                constraint="uq_datasets_name_source",
                set_={"file_name": csv_path.name, "updated_at": func.now()},
            )
            .returning(Dataset.id)
        )
        dataset_id = session.execute(dataset_stmt).scalar_one()

        record_stmt = (
            insert(ElectricityConsumption)
            .values([{**row, "dataset_id": dataset_id} for row in rows])
            .on_conflict_do_nothing(index_elements=[
                ElectricityConsumption.country_id,
                ElectricityConsumption.month,
                ElectricityConsumption.metric,
                func.coalesce(ElectricityConsumption.fuel, literal_column("''")),
            ])
            .returning(ElectricityConsumption.id)
        )
        result = session.execute(record_stmt)
        inserted = len(result.scalars().all())

        total_for_dataset = session.scalar(
            select(func.count()).select_from(ElectricityConsumption).where(
                ElectricityConsumption.dataset_id == dataset_id
            )
        ) or 0
        session.execute(
            Dataset.__table__.update()
            .where(Dataset.id == dataset_id)
            .values(
                record_count=total_for_dataset,
                start_date=min(row["month"] for row in rows),
                end_date=max(row["month"] for row in rows),
                status="imported",
                updated_at=func.now(),
            )
        )
    return inserted, len(rows) - inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "vietnam_electricity_demand.csv",
        help="Processed CSV path (defaults to the repository dataset).",
    )
    args = parser.parse_args()

    try:
        rows = load_rows(args.file)
        inserted, skipped = import_rows(rows, args.file)
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    print(f"CSV rows validated: {len(rows)}")
    print(f"Records inserted: {inserted}")
    print(f"Duplicate records skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
