from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import Dataset, DatasetImport, ElectricityConsumption, NEMObservation
from app.nem.schemas import NEMObservationRecord
from app.services import nem_import
from app.services.nem_import import NEMImportError, import_nem_observations


def observation(
    metric="demand",
    interval="5m",
    observed_at="2026-11-23T00:00:00+10:00",
    value="20628.55",
    unit="MW",
    result="demand_total",
    grouping_type="network",
    grouping_code="",
):
    return NEMObservationRecord(
        network_code="NEM",
        metric=metric,
        interval=interval,
        observed_at=datetime.fromisoformat(observed_at),
        value=Decimal(value),
        unit=unit,
        result=result,
        grouping_type=grouping_type,
        grouping_code=grouping_code,
    )


def nem_dataset(db_session):
    return db_session.scalar(
        select(Dataset).where(Dataset.name == "Open Electricity NEM")
    )


def test_first_import_creates_nem_dataset_and_observations(db_session):
    imported = import_nem_observations(
        db_session,
        [
            observation(observed_at="2026-11-23T00:00:00+10:00"),
            observation(observed_at="2026-11-23T00:05:00+10:00", value="20631.125"),
        ],
    )

    dataset = nem_dataset(db_session)
    assert dataset is not None
    assert dataset.name == "Open Electricity NEM"
    assert dataset.source == nem_import.NEM_DATASET_SOURCE
    assert dataset.file_name == "Open Electricity API observations"
    assert "Open Electricity API" in dataset.description
    assert dataset.status == "ready"
    assert dataset.record_count == 2
    assert dataset.start_date.isoformat() == "2026-11-23"
    assert dataset.end_date.isoformat() == "2026-11-23"
    assert imported.dataset_id == dataset.id
    assert imported.mode == "nem_api_5m"
    assert imported.status == "completed"
    assert imported.rows_read == 2
    assert imported.inserted_count == 2
    assert imported.updated_count == 0
    assert imported.skipped_count == 0
    assert imported.error_count == 0
    assert imported.started_at is not None and imported.completed_at is not None
    assert db_session.scalar(
        select(func.count()).select_from(NEMObservation).where(NEMObservation.dataset_id == dataset.id)
    ) == 2


def test_existing_dataset_with_matching_name_and_source_is_reused(db_session):
    dataset = Dataset(
        name=nem_import.NEM_DATASET_NAME,
        source=nem_import.NEM_DATASET_SOURCE,
        file_name="existing API metadata",
        record_count=0,
        status="importing",
    )
    db_session.add(dataset)
    db_session.commit()
    dataset_id = dataset.id

    imported = import_nem_observations(db_session, [observation()])

    reused = db_session.get(Dataset, dataset_id)
    assert imported.dataset_id == dataset_id
    assert reused.source == nem_import.NEM_DATASET_SOURCE
    assert db_session.scalar(select(func.count()).select_from(Dataset)) == 1


def test_same_dataset_name_with_different_source_is_not_modified(db_session):
    conflicting = Dataset(
        name=nem_import.NEM_DATASET_NAME,
        source="https://example.invalid/another-source",
        file_name="do-not-change.csv",
        description="Existing unrelated dataset",
        record_count=1,
        status="ready",
    )
    db_session.add(conflicting)
    db_session.flush()
    old_observation = NEMObservation(
        dataset_id=conflicting.id,
        network_code="NEM",
        metric="demand",
        interval="5m",
        observed_at=datetime.fromisoformat("2026-11-22T00:00:00+10:00"),
        value=Decimal("123.000000"),
        unit="MW",
        result="demand_total",
        grouping_type="network",
        grouping_code="",
    )
    vnm = Dataset(
        name="Vietnam monthly demand",
        source="Ember fixture",
        file_name="vietnam.csv",
        record_count=0,
        status="imported",
    )
    db_session.add_all([old_observation, vnm])
    db_session.commit()
    conflict_id = conflicting.id
    old_observation_id = old_observation.id
    vnm_id = vnm.id

    with pytest.raises(NEMImportError, match="different source"):
        import_nem_observations(db_session, [observation()])

    unchanged = db_session.get(Dataset, conflict_id)
    assert unchanged.name == nem_import.NEM_DATASET_NAME
    assert unchanged.source == "https://example.invalid/another-source"
    assert unchanged.file_name == "do-not-change.csv"
    assert unchanged.description == "Existing unrelated dataset"
    assert unchanged.record_count == 1
    assert unchanged.status == "ready"
    retained_observation = db_session.get(NEMObservation, old_observation_id)
    assert retained_observation.dataset_id == conflict_id
    assert retained_observation.value == Decimal("123.000000")
    unchanged_vnm = db_session.get(Dataset, vnm_id)
    assert unchanged_vnm.source == "Ember fixture"
    assert db_session.scalar(select(func.count()).select_from(DatasetImport)) == 0
    assert db_session.scalar(select(func.count()).select_from(NEMObservation)) == 1


def test_reimport_reuses_dataset_and_counts_insert_update_skip_exactly(db_session):
    first = import_nem_observations(
        db_session,
        [
            observation(observed_at="2026-11-23T00:00:00+10:00", value="10"),
            observation(observed_at="2026-11-23T00:05:00+10:00", value="20"),
        ],
    )
    dataset_id = first.dataset_id

    second = import_nem_observations(
        db_session,
        [
            observation(observed_at="2026-11-23T00:00:00+10:00", value="10"),
            observation(observed_at="2026-11-23T00:05:00+10:00", value="21"),
            observation(observed_at="2026-11-23T00:10:00+10:00", value="30"),
        ],
    )

    assert second.dataset_id == dataset_id
    assert second.inserted_count == 1
    assert second.updated_count == 1
    assert second.skipped_count == 1
    assert second.rows_read == 3
    assert db_session.scalar(select(func.count()).select_from(Dataset)) == 1
    assert db_session.scalar(
        select(func.count()).select_from(NEMObservation).where(NEMObservation.dataset_id == dataset_id)
    ) == 3
    updated = db_session.scalar(
        select(NEMObservation).where(
            NEMObservation.dataset_id == dataset_id,
            NEMObservation.observed_at == datetime.fromisoformat("2026-11-23T00:05:00+10:00"),
        )
    )
    assert updated.value == Decimal("21.000000")


def test_daily_batch_supports_multiple_metrics_and_daily_mode(db_session):
    imported = import_nem_observations(
        db_session,
        [
            observation(
                metric="demand",
                interval="1d",
                observed_at="2026-11-23T00:00:00+10:00",
                value="20000",
                unit="MW",
                result="demand_total",
            ),
            observation(
                metric="price",
                interval="1d",
                observed_at="2026-11-23T00:00:00+10:00",
                value="-12.5",
                unit="AUD/MWh",
                result="price_result",
            ),
            observation(
                metric="demand_energy",
                interval="1d",
                observed_at="2026-11-23T00:00:00+10:00",
                value="480000",
                unit="MWh",
                result="demand_energy_result",
            ),
        ],
    )

    assert imported.mode == "nem_api_daily"
    assert imported.inserted_count == 3
    assert imported.updated_count == 0
    assert imported.skipped_count == 0
    prices = db_session.scalars(
        select(NEMObservation).where(NEMObservation.metric == "price")
    ).all()
    assert len(prices) == 1
    assert prices[0].value == Decimal("-12.500000")


def test_separate_five_minute_and_daily_import_modes_share_dataset(db_session):
    five_minute = import_nem_observations(db_session, [observation()])
    daily = import_nem_observations(
        db_session,
        [
            observation(
                metric="demand",
                interval="1d",
                observed_at="2026-11-24T00:00:00+10:00",
                value="20100",
                unit="MW",
            )
        ],
    )

    assert five_minute.mode == "nem_api_5m"
    assert daily.mode == "nem_api_daily"
    assert five_minute.dataset_id == daily.dataset_id
    dataset = nem_dataset(db_session)
    assert dataset.record_count == 2
    assert dataset.start_date.isoformat() == "2026-11-23"
    assert dataset.end_date.isoformat() == "2026-11-24"


def test_duplicate_natural_keys_in_batch_fail_without_partial_rows(db_session):
    duplicate_a = observation(value="1")
    duplicate_b = observation(value="2")

    with pytest.raises(NEMImportError, match="duplicate natural keys"):
        import_nem_observations(db_session, [duplicate_a, duplicate_b])

    dataset = nem_dataset(db_session)
    history = db_session.scalar(select(DatasetImport))
    assert dataset is not None
    assert history.status == "failed"
    assert history.mode == "nem_api_5m"
    assert history.rows_read == 2
    assert history.error_count == 1
    assert history.error_message == "observation batch contains duplicate natural keys"
    assert history.completed_at is not None
    assert db_session.scalar(select(func.count()).select_from(NEMObservation)) == 0
    assert dataset.status == "failed"


def test_observation_transaction_rolls_back_but_failed_history_persists(db_session, monkeypatch):
    def fail_after_upsert(_db, _dataset_id, _records):
        raise RuntimeError("private detail with API key must not be persisted")

    monkeypatch.setattr(nem_import, "_refresh_dataset_metadata", fail_after_upsert)

    with pytest.raises(RuntimeError, match="private detail"):
        import_nem_observations(db_session, [observation()])

    dataset = nem_dataset(db_session)
    history = db_session.scalar(select(DatasetImport))
    assert dataset is not None
    assert history.status == "failed"
    assert history.error_count == 1
    assert history.error_message == "NEM import failed (RuntimeError)"
    assert "private detail" not in history.error_message
    assert db_session.scalar(select(func.count()).select_from(NEMObservation)) == 0
    assert dataset.record_count == 0
    assert dataset.status == "failed"


def test_import_does_not_modify_vnm_dataset_or_consumption(db_session):
    vnm = Dataset(
        name="Vietnam monthly demand",
        source="Ember fixture",
        file_name="vietnam.csv",
        record_count=1,
        status="imported",
    )
    db_session.add(vnm)
    db_session.flush()
    consumption = ElectricityConsumption(
        dataset_id=vnm.id,
        country_id="vietnam",
        country="Vietnam",
        iso3="VNM",
        month=datetime(2026, 9, 1).date(),
        metric="demand",
        fuel=None,
        value=Decimal("17.8700"),
        unit="TWh",
    )
    db_session.add(consumption)
    db_session.commit()
    vnm_id = vnm.id
    consumption_id = consumption.id

    import_nem_observations(db_session, [observation()])

    unchanged_vnm = db_session.get(Dataset, vnm_id)
    unchanged_consumption = db_session.get(ElectricityConsumption, consumption_id)
    assert unchanged_vnm.record_count == 1
    assert unchanged_vnm.status == "imported"
    assert unchanged_vnm.start_date is None
    assert unchanged_vnm.end_date is None
    assert unchanged_consumption.dataset_id == vnm_id
    assert unchanged_consumption.iso3 == "VNM"
    assert unchanged_consumption.value == Decimal("17.8700")
    assert db_session.scalar(select(func.count()).select_from(Dataset)) == 2
