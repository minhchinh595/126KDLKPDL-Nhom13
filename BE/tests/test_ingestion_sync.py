from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes import datasets



def test_sync_is_disabled_without_fetching_or_calling_ingestion(monkeypatch):
    db = MagicMock()
    monkeypatch.setenv("DATASET_SYNC_URL", "https://data.example.test/monthly.csv")

    def unexpected(*_args, **_kwargs):
        raise AssertionError("disabled sync must not fetch or normalize CSV")

    monkeypatch.setattr(datasets, "urlopen", unexpected, raising=False)
    monkeypatch.setattr(datasets.ingestion_service_client, "normalize", unexpected)

    with pytest.raises(HTTPException) as error:
        datasets.sync_dataset(db)

    assert error.value.status_code == 410
    assert "Open Electricity NEM" in error.value.detail
    db.scalar.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()
