from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.services.nem_data import NEMDatasetUnavailable
from app.services.nem_ml_data import NEMMLDataError, load_nem_clustering_input


BRISBANE = ZoneInfo("Australia/Brisbane")


class Result:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class Session:
    def __init__(self, dataset, rows):
        self.dataset = dataset
        self.rows = rows
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        return Result(([self.dataset] if self.dataset is not None else []) if len(self.statements) == 1 else self.rows)


def nem_dataset():
    return SimpleNamespace(
        id=4,
        name="Open Electricity NEM",
        source="https://api.openelectricity.org.au/v4/market/network/NEM",
    )


def make_rows(count=20, start=date(2026, 1, 1), *, missing=None, missing_metric=None, outlier=False):
    rows = []
    unit_by_metric = {
        "demand": "MW",
        "generation_renewable": "MW",
        "price": "$/MWh",
        "renewable_proportion": "%",
    }
    for offset in range(count):
        if offset == missing and missing_metric is None:
            continue
        current = start + timedelta(days=offset)
        values = {
            "demand": Decimal(20_000 + 500 * (offset % 7) + (100_000 if outlier and offset == 4 else 0)),
            "generation_renewable": Decimal(8_000 + 350 * ((offset * 3) % 9)),
            "price": Decimal(-12 if offset == 2 else 40 + 2 * ((offset * 5) % 13)),
            "renewable_proportion": Decimal(30 + (offset * 7) % 30),
        }
        for metric, value in values.items():
            if offset == missing and metric == missing_metric:
                continue
            rows.append(SimpleNamespace(
                id=len(rows) + 1,
                dataset_id=4,
                network_code="NEM",
                metric=metric,
                interval="1d",
                observed_at=datetime.combine(current, datetime.min.time(), tzinfo=BRISBANE),
                value=value,
                unit=unit_by_metric[metric],
                result="NEM",
                grouping_type="network",
                grouping_code="",
            ))
    return rows


def test_loader_builds_a_and_b_from_exact_nem_network_daily_rows():
    session = Session(nem_dataset(), make_rows())
    loaded = load_nem_clustering_input(session)
    payload = loaded.as_service_payload()
    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "nem_observations.dataset_id = 4" in sql
    assert "nem_observations.network_code = 'NEM'" in sql
    assert "nem_observations.interval = '1d'" in sql
    assert "nem_observations.grouping_type = 'network'" in sql
    assert "nem_observations.grouping_code = ''" in sql
    assert payload["network_code"] == "NEM" and payload["interval"] == "1d"
    assert payload["configurations"]["A"]["feature_names"] == ["demand", "generation_renewable", "price"]
    assert payload["configurations"]["B"]["feature_names"] == ["demand", "generation_renewable", "price", "renewable_proportion"]
    assert "demand_energy" not in payload["configurations"]["A"]["feature_names"]
    assert "demand_energy" not in payload["configurations"]["B"]["feature_names"]
    assert payload["configurations"]["A"]["observation_count"] == 20
    assert payload["configurations"]["B"]["observation_count"] == 20
    assert payload["configurations"]["A"]["feature_units"]["price"] == "$/MWh"
    assert payload["configurations"]["A"]["records"][2]["features"]["price"] == -12.0


def test_model_a_retains_days_that_model_b_drops_for_missing_proportion():
    rows = make_rows(count=20, missing=5, missing_metric="renewable_proportion")
    payload = load_nem_clustering_input(Session(nem_dataset(), rows)).as_service_payload()
    a = payload["configurations"]["A"]
    b = payload["configurations"]["B"]
    assert a["observation_count"] == 20
    assert b["observation_count"] == 19
    assert b["dropped_date_count"] == 1
    assert b["dropped_reasons"] == {"missing:renewable_proportion": 1}


def test_loader_reports_full_span_gaps_and_keeps_iqr_outliers_and_negative_prices():
    rows = make_rows(count=20, missing=9, outlier=True)
    payload = load_nem_clustering_input(Session(nem_dataset(), rows)).as_service_payload()
    a = payload["configurations"]["A"]
    assert a["metric_quality"]["demand"]["missing_dates"] == ["2026-01-10"]
    assert a["metric_quality"]["demand"]["iqr_outlier_count"] >= 1
    assert len(a["records"]) == 19
    assert any(record["features"]["demand"] > 100_000 for record in a["records"])
    assert any(record["features"]["price"] < 0 for record in a["records"])
    assert a["metric_quality"]["price"]["negative_count"] == 1


def test_duplicate_local_date_is_reported_and_excluded_without_choosing_a_row():
    rows = make_rows(count=20)
    duplicate = SimpleNamespace(**vars(rows[0]))
    duplicate.id = 9999
    duplicate.result = "OTHER"
    rows.append(duplicate)
    payload = load_nem_clustering_input(Session(nem_dataset(), rows)).as_service_payload()
    a = payload["configurations"]["A"]
    assert a["metric_quality"]["demand"]["duplicate_local_dates"] == 1
    assert a["dropped_reasons"] == {"duplicate_local_date:demand": 1}
    assert len(a["records"]) == 19


def test_loader_rejects_multiple_unit_labels_and_missing_or_ambiguous_nem_dataset():
    rows = make_rows(count=20)
    rows[0].unit = "kW"
    with pytest.raises(NEMMLDataError, match="inconsistent unit"):
        load_nem_clustering_input(Session(nem_dataset(), rows))
    with pytest.raises(NEMDatasetUnavailable):
        load_nem_clustering_input(Session(None, rows))


@pytest.mark.parametrize(
    "metric,wrong_unit",
    [("demand", "kW"), ("generation_renewable", "kW"), ("price", "AUD/MWh"),
     ("renewable_proportion", "percent")],
)
def test_clustering_rejects_consistently_wrong_metric_unit(metric, wrong_unit):
    rows = make_rows(count=5)
    for row in rows:
        if row.metric == metric:
            row.unit = wrong_unit
    with pytest.raises(NEMMLDataError, match="requires unit"):
        load_nem_clustering_input(Session(nem_dataset(), rows))


@pytest.mark.parametrize(
    "metric,value",
    [("demand", "-1"), ("generation_renewable", "-1"),
     ("renewable_proportion", "-0.1"), ("renewable_proportion", "100.1")],
)
def test_clustering_rejects_metric_domain_violations(metric, value):
    rows = make_rows(count=5)
    target = next(row for row in rows if row.metric == metric)
    target.value = Decimal(value)
    with pytest.raises(NEMMLDataError, match=r"negative value|within \[0, 100\]"):
        load_nem_clustering_input(Session(nem_dataset(), rows))
