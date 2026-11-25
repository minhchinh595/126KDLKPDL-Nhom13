from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Dataset, NEMObservation
from app.services.nem_data import NEMDatasetUnavailable, query_observations, resolve_nem_dataset
from app.services.nem_import import NEM_DATASET_NAME, NEM_DATASET_SOURCE


class _ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _ResolverDB:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, _statement):
        return _ScalarResult(self.rows)


def test_resolver_reports_missing_and_ambiguous_dataset():
    with pytest.raises(NEMDatasetUnavailable, match="not available"):
        resolve_nem_dataset(_ResolverDB([]))
    with pytest.raises(NEMDatasetUnavailable, match="ambiguous"):
        resolve_nem_dataset(_ResolverDB([object(), object()]))


def test_query_filters_exact_dataset_metric_interval_and_half_open_time(db_session):
    dataset = Dataset(name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE, file_name="API", record_count=5)
    other = Dataset(name="Other data", source="other", file_name="other", record_count=1)
    db_session.add_all([dataset, other])
    db_session.flush()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add_all([
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="price", interval="1d", observed_at=start, value=-10, unit="$/MWh", result="NEM", grouping_type="network", grouping_code=""),
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="price", interval="1d", observed_at=start + timedelta(days=1), value=20, unit="$/MWh", result="NEM", grouping_type="network", grouping_code=""),
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="demand", interval="1d", observed_at=start, value=100, unit="MW", result="NEM", grouping_type="network", grouping_code=""),
        # Same metric/interval and inside the requested range, but in another Dataset.
        # Its timestamp differs so it cannot violate the global natural key.
        NEMObservation(dataset_id=other.id, network_code="NEM", metric="price", interval="1d", observed_at=start + timedelta(hours=12), value=999, unit="$/MWh", result="NEM", grouping_type="network", grouping_code=""),
        # Same metric in a different supported interval, inside the range.
        NEMObservation(dataset_id=dataset.id, network_code="NEM", metric="demand", interval="5m", observed_at=start + timedelta(minutes=30), value=500, unit="MW", result="NEM", grouping_type="network", grouping_code=""),
    ])
    db_session.flush()
    resolved, rows, total = query_observations(db_session, metric="price", interval="1d", start_at=start, end_at=start + timedelta(days=1))
    assert resolved.id == dataset.id
    assert total == 1 and len(rows) == 1
    assert float(rows[0].value) == -10


def test_query_rejects_naive_timestamps_and_unbounded_five_minute_access(db_session):
    db_session.add(Dataset(name=NEM_DATASET_NAME, source=NEM_DATASET_SOURCE, file_name="API"))
    db_session.flush()
    naive = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        query_observations(db_session, metric="demand", interval="1d", start_at=naive)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="require start_at and end_at"):
        query_observations(db_session, metric="demand", interval="5m")
    with pytest.raises(ValueError, match="cannot exceed 7 days"):
        query_observations(db_session, metric="demand", interval="5m", start_at=start, end_at=start + timedelta(days=8))
