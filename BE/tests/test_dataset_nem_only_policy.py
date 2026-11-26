import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import datasets
from app.schemas.datasets import DatasetPublic
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE


def _dataset(*, name="Vietnam electricity demand", source="Ember"):
    return SimpleNamespace(
        id=17,
        name=name,
        source=source,
        file_name="legacy.csv",
        description="Retained historical dataset",
        record_count=93,
        start_date=date(2019, 1, 1),
        end_date=date(2026, 9, 1),
        status="imported",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class _FakeDB:
    def __init__(self, dataset=None):
        self.dataset = dataset
        self.writes = 0

    def get(self, _model, _identity):
        return self.dataset

    def add(self, *_args, **_kwargs):
        self.writes += 1

    def commit(self):
        self.writes += 1


def test_dataset_metadata_marks_nem_active_and_vnm_legacy():
    legacy = DatasetPublic.model_validate(_dataset())
    nem = DatasetPublic.model_validate(
        _dataset(name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE)
    )

    assert legacy.source_role == "legacy"
    assert nem.source_role == "active_nem"
    assert legacy.model_dump()["source_role"] == "legacy"


def test_csv_upload_is_disabled_before_file_or_database_write():
    db = _FakeDB()

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            datasets.upload_dataset(
                file=object(), name="VNM CSV", source="Ember", description=None, db=db
            )
        )

    assert error.value.status_code == 410
    assert "Open Electricity NEM" in error.value.detail
    assert db.writes == 0


def test_import_rejects_legacy_dataset_without_calling_csv_ingestion(monkeypatch):
    db = _FakeDB(_dataset())

    def unexpected(*_args, **_kwargs):
        raise AssertionError("CSV Ingestion must not be called")

    monkeypatch.setattr(datasets.ingestion_service_client, "normalize", unexpected)
    monkeypatch.setattr(datasets, "import_dataset_file", unexpected)

    with pytest.raises(HTTPException) as error:
        datasets.import_dataset(17, db)

    assert error.value.status_code == 410
    assert db.writes == 0


def test_import_of_missing_dataset_remains_not_found():
    with pytest.raises(HTTPException) as error:
        datasets.import_dataset(999, _FakeDB())

    assert error.value.status_code == 404


def test_sync_is_disabled_without_reading_url_or_calling_csv_services(monkeypatch):
    db = _FakeDB()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("legacy sync side effect must not occur")

    monkeypatch.setenv("DATASET_SYNC_URL", "https://example.invalid/vnm.csv")
    monkeypatch.setattr(datasets, "urlopen", unexpected, raising=False)
    monkeypatch.setattr(datasets.ingestion_service_client, "normalize", unexpected)
    monkeypatch.setattr(datasets, "import_dataset_file", unexpected)

    with pytest.raises(HTTPException) as error:
        datasets.sync_dataset(db)

    assert error.value.status_code == 410
    assert db.writes == 0


def test_nem_public_electricity_routes_remain_registered():
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/electricity/demand" in paths
    assert "/api/electricity/observations" in paths


def test_compose_marks_csv_ingestion_as_opt_in_and_nem_worker_separately():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    ingestion_block = compose.split("\n  ingestion:\n", 1)[1].split(
        "\n  nem-ingestion-worker:", 1
    )[0]
    worker_block = compose.split("\n  nem-ingestion-worker:\n", 1)[1].split(
        "\n  frontend:", 1
    )[0]
    gateway_block = compose.split("\n  gateway:\n", 1)[1].split(
        "\n  analysis:", 1
    )[0]

    assert 'profiles: ["legacy-csv"]' in ingestion_block
    assert 'profiles: ["nem-ingestion"]' in worker_block
    assert "      ingestion:" not in gateway_block
