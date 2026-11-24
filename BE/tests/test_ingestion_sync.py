import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes import datasets
from app.clients.ingestion import IngestionServiceUnavailable


VALID_CSV = (
    b"country_id,country,iso3,month,metric,fuel,value,unit\n"
    b"vietnam,Vietnam,VNM,2026-09,demand,,17.87,TWh\n"
)


class RemoteCSV:
    headers = {"Content-Type": "text/csv; charset=utf-8"}

    def __init__(self):
        self.sent = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        if self.sent:
            return b""
        self.sent = True
        return VALID_CSV


def test_sync_cleans_downloaded_file_when_ingestion_service_returns_503(monkeypatch):
    dataset = MagicMock()
    dataset.id = 91
    dataset.status = "imported"
    dataset.storage_key = "previous-upload.csv"
    db = MagicMock()
    db.scalar.return_value = dataset

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
        upload_dir = Path(temp_dir)
        monkeypatch.setenv("DATASET_SYNC_URL", "https://data.example.test/monthly.csv")
        monkeypatch.setattr(datasets, "UPLOAD_DIR", upload_dir)
        monkeypatch.setattr(datasets, "urlopen", lambda *_args, **_kwargs: RemoteCSV())

        def unavailable(_content):
            raise IngestionServiceUnavailable("Ingestion Service is unavailable")

        monkeypatch.setattr(datasets.ingestion_service_client, "normalize", unavailable)

        with pytest.raises(HTTPException) as error:
            datasets.sync_dataset(db)

        assert error.value.status_code == 503
        assert error.value.detail == "Ingestion Service is unavailable"
        assert list(upload_dir.iterdir()) == []
        assert dataset.storage_key == "previous-upload.csv"
        assert dataset.status == "imported"
        db.add.assert_not_called()
        db.commit.assert_not_called()
