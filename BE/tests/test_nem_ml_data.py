from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.services import nem_ml_data
from app.services.nem_data import NEMDatasetUnavailable


BRISBANE = ZoneInfo("Australia/Brisbane")


class FakeResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeSession:
    def __init__(self, datasets=(), rows=()):
        self.datasets = list(datasets)
        self.rows = list(rows)
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return FakeResult(self.datasets)
        return FakeResult(self.rows)


def dataset():
    return SimpleNamespace(
        id=17,
        name="Open Electricity NEM",
        source="https://api.openelectricity.org.au/v4/market/network/NEM",
    )


def observation(day, value, *, unit="MW", network="NEM", metric="demand", interval="1d", grouping="network", code="", result="NEM", at=None):
    observed_at = at or datetime.combine(day, datetime.min.time(), tzinfo=BRISBANE)
    return SimpleNamespace(
        id=day.toordinal(),
        dataset_id=17,
        network_code=network,
        metric=metric,
        interval=interval,
        observed_at=observed_at,
        value=value,
        unit=unit,
        result=result,
        grouping_type=grouping,
        grouping_code=code,
    )


def load_rows(rows):
    return nem_ml_data.load_nem_daily_demand(FakeSession([dataset()], rows))


def continuous_data(count=40, start=date(2026, 1, 1)):
    rows = [observation(start + timedelta(days=offset), Decimal(100 + offset)) for offset in range(count)]
    return load_rows(rows)


def test_resolver_requires_one_exact_nem_dataset_and_never_falls_back():
    with pytest.raises(NEMDatasetUnavailable, match="not available"):
        nem_ml_data.load_nem_daily_demand(FakeSession([], []))
    with pytest.raises(NEMDatasetUnavailable, match="ambiguous"):
        nem_ml_data.load_nem_daily_demand(FakeSession([dataset(), dataset()], []))


def test_loader_filters_network_metric_interval_grouping_and_unit_and_orders_rows():
    start = date(2026, 1, 1)
    rows = [
        observation(start + timedelta(days=1), Decimal("102")),
        observation(start, Decimal("101")),
    ]
    # Query predicates are inspectable; only exact accepted unit records enter the ML rows.
    session = FakeSession([dataset()], rows)
    loaded = nem_ml_data.load_nem_daily_demand(session)
    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    for predicate in (
        "nem_observations.dataset_id = 17",
        "nem_observations.network_code = 'NEM'",
        "nem_observations.metric = 'demand'",
        "nem_observations.interval = '1d'",
        "nem_observations.grouping_type = 'network'",
        "nem_observations.grouping_code = ''",
    ):
        assert predicate in sql
    assert [row.local_date for row in loaded.observations] == [start, start + timedelta(days=1)]
    assert loaded.unit_mismatch_count == 0
    assert loaded.missing_dates == ()


@pytest.mark.parametrize(
    "metric,unit",
    [("demand", "MW"), ("generation_renewable", "MW"), ("price", "$/MWh"),
     ("renewable_proportion", "%"), ("demand_energy", "MWh")],
)
def test_daily_metric_enforces_expected_unit_contract(metric, unit):
    row = observation(date(2026, 1, 1), Decimal("1"), metric=metric, unit=unit)
    loaded = nem_ml_data.load_nem_daily_metric(
        FakeSession([dataset()], [row]), metric=metric, unit=unit
    )
    assert loaded.unit == unit
    assert loaded.observation_count == 1


def test_daily_metric_rejects_wrong_requested_or_observed_unit_without_conversion():
    demand = observation(date(2026, 1, 1), Decimal("1"), unit="kW")
    with pytest.raises(nem_ml_data.NEMMLDataError, match="requires unit 'MW'"):
        nem_ml_data.load_nem_daily_metric(FakeSession([dataset()], [demand]), metric="demand", unit="kW")
    with pytest.raises(nem_ml_data.NEMMLDataError, match="incompatible unit label.*kW"):
        nem_ml_data.load_nem_daily_metric(FakeSession([dataset()], [demand]), metric="demand", unit="MW")

    inconsistent = [
        observation(date(2026, 1, 1), Decimal("1"), unit="MW"),
        observation(date(2026, 1, 2), Decimal("2"), unit="kW"),
    ]
    with pytest.raises(nem_ml_data.NEMMLDataError, match="incompatible unit label"):
        nem_ml_data.load_nem_daily_metric(FakeSession([dataset()], inconsistent), metric="demand", unit="MW")


@pytest.mark.parametrize(
    "metric,unit,value",
    [("demand", "MW", "-0.1"), ("generation_renewable", "MW", "-1"),
     ("demand_energy", "MWh", "-1"), ("renewable_proportion", "%", "-0.01"),
     ("renewable_proportion", "%", "100.01")],
)
def test_daily_metric_rejects_values_outside_metric_domain(metric, unit, value):
    row = observation(date(2026, 1, 1), Decimal(value), metric=metric, unit=unit)
    with pytest.raises(nem_ml_data.NEMMLDataError, match=r"negative value|within \[0, 100\]"):
        nem_ml_data.load_nem_daily_metric(FakeSession([dataset()], [row]), metric=metric, unit=unit)


def test_daily_metric_allows_negative_price_and_preserves_outlier_and_gaps():
    start = date(2026, 1, 1)
    rows = [
        observation(start, Decimal("-500"), metric="price", unit="$/MWh"),
        observation(start + timedelta(days=2), Decimal("40000"), metric="price", unit="$/MWh"),
    ]
    loaded = nem_ml_data.load_nem_daily_metric(
        FakeSession([dataset()], rows), metric="price", unit="$/MWh"
    )
    assert [item.value for item in loaded.observations] == [Decimal("-500"), Decimal("40000")]
    assert loaded.negative_count == 1
    assert loaded.missing_dates == (start + timedelta(days=1),)


def test_loader_reports_gaps_duplicates_invalids_and_does_not_fill_them():
    day = date(2026, 2, 1)
    rows = [
        observation(day, Decimal("0")),
        observation(day + timedelta(days=2), Decimal("2")),
        observation(day + timedelta(days=2), Decimal("3"), result="OTHER"),
        observation(day + timedelta(days=3), None),
    ]
    loaded = load_rows(rows)
    assert loaded.observation_count == 4
    assert loaded.missing_dates == (day + timedelta(days=1),)
    duplicate_instant = datetime.combine(
        day + timedelta(days=2), datetime.min.time(), tzinfo=BRISBANE
    ).astimezone(timezone.utc).isoformat()
    assert loaded.duplicate_timestamps == (duplicate_instant,)
    assert loaded.duplicate_local_dates == ((day + timedelta(days=2)).isoformat(),)
    assert loaded.null_value_count == 1
    assert loaded.zero_count == 1
    assert loaded.negative_count == 0
    assert loaded.observations[0].value == Decimal("0")


def test_loader_reports_timezone_naive_timestamp_and_builder_rejects_it():
    loaded = load_rows([observation(date(2026, 1, 1), Decimal("10"), at=datetime(2026, 1, 1))])
    assert loaded.timezone_naive_count == 1
    with pytest.raises(nem_ml_data.NEMMLDataError, match="timezone-naive"):
        nem_ml_data.build_daily_supervised_features(loaded)


def test_daily_loader_metadata_and_provenance_are_json_compatible():
    loaded = continuous_data(3)
    provenance = loaded.provenance(["demand_at_cutoff", "day_of_week"])
    assert provenance == {
        "dataset_name": "Open Electricity NEM",
        "dataset_source": "https://api.openelectricity.org.au/v4/market/network/NEM",
        "dataset_id": 17,
        "network_code": "NEM",
        "metric": "demand",
        "interval": "1d",
        "unit": "MW",
        "training_start": "2026-01-01",
        "training_end": "2026-01-03",
        "observation_count": 3,
        "feature_names": ["demand_at_cutoff", "day_of_week"],
        "data_fingerprint": loaded.data_fingerprint,
    }
    assert len(loaded.data_fingerprint) == 64
    changed = load_rows([observation(date(2026, 1, 1), Decimal("101")), observation(date(2026, 1, 2), Decimal("102")), observation(date(2026, 1, 3), Decimal("103"))])
    assert changed.data_fingerprint != loaded.data_fingerprint


def test_fixed_horizon_features_use_cutoff_observations_and_known_calendar_features():
    loaded = continuous_data(40)
    samples = nem_ml_data.build_daily_supervised_features(loaded)
    assert samples.feature_names == (
        "demand_at_cutoff", "demand_6d_before_cutoff", "demand_13d_before_cutoff", "demand_27d_before_cutoff",
        "day_of_week", "day_of_year",
    )
    assert samples.target_name == "demand" and samples.target_unit == "MW"
    assert samples.valid_sample_count == 11
    assert samples.exclusion_reasons == {"missing_lag_observation": 29}
    assert samples.valid_samples_by_lag == {
        "demand_at_cutoff": 38,
        "demand_6d_before_cutoff": 32,
        "demand_13d_before_cutoff": 25,
        "demand_27d_before_cutoff": 11,
    }
    target_day = date(2026, 1, 30)
    target_index = next(i for i, ts in enumerate(samples.target_timestamps) if ts.date() == target_day)
    assert samples.cutoff_dates[target_index] == date(2026, 1, 28)
    assert target_day - samples.cutoff_dates[target_index] == timedelta(days=2)
    assert samples.features[target_index] == {
        "demand_at_cutoff": 127.0,
        "demand_6d_before_cutoff": 121.0,
        "demand_13d_before_cutoff": 114.0,
        "demand_27d_before_cutoff": 100.0,
        "day_of_week": float(target_day.weekday()),
        "day_of_year": float(target_day.timetuple().tm_yday),
    }
    assert "target" not in samples.features[target_index]


def test_feature_builder_excludes_gap_samples_without_zero_imputation():
    start = date(2026, 1, 1)
    rows = [observation(start + timedelta(days=i), Decimal(200 + i)) for i in range(35) if i != 14]
    loaded = load_rows(rows)
    samples = nem_ml_data.build_daily_supervised_features(loaded)
    assert samples.exclusion_reasons["missing_lag_observation"] > 0
    assert all(value != 0 for row in samples.features for name, value in row.items() if name.startswith("demand_"))
    assert date(2026, 1, 30) not in {ts.date() for ts in samples.target_timestamps}


def test_features_for_a_target_do_not_depend_on_that_or_future_demand():
    initial = continuous_data(40)
    base = nem_ml_data.build_daily_supervised_features(initial)
    changed_rows = [observation(date(2026, 1, 1) + timedelta(days=i), Decimal(100 + i + (500 if i >= 29 else 0))) for i in range(40)]
    changed = nem_ml_data.build_daily_supervised_features(load_rows(changed_rows))
    target_day = date(2026, 1, 30)
    base_i = next(i for i, ts in enumerate(base.target_timestamps) if ts.date() == target_day)
    changed_i = next(i for i, ts in enumerate(changed.target_timestamps) if ts.date() == target_day)
    assert base.features[base_i] == changed.features[changed_i]
    assert base.target[base_i] != changed.target[changed_i]


def test_feature_builder_rejects_duplicates_and_non_demand_units():
    day = date(2026, 1, 1)
    duplicate = load_rows([observation(day, Decimal(1)), observation(day, Decimal(2), result="OTHER")])
    with pytest.raises(nem_ml_data.NEMMLDataError, match="duplicate"):
        nem_ml_data.build_daily_supervised_features(duplicate)
    wrong_unit = replace(continuous_data(2), unit="MWh")
    with pytest.raises(nem_ml_data.NEMMLDataError, match="MW"):
        nem_ml_data.build_daily_supervised_features(wrong_unit)


def test_brisbane_clock_and_fixed_horizon_dates_support_utc_inputs():
    as_of, cutoff, target = nem_ml_data.nem_forecast_dates(
        datetime(2026, 2, 10, 14, 30, tzinfo=timezone.utc)
    )
    assert (as_of, cutoff, target) == (
        date(2026, 2, 11), date(2026, 2, 10), date(2026, 2, 12)
    )


def test_tomorrow_forecast_uses_only_cutoff_and_earlier_feature_dates():
    start = date(2026, 1, 1)
    rows = [observation(start + timedelta(days=i), Decimal(100 + i)) for i in range(40)]
    rows.append(observation(date(2026, 2, 10), Decimal(999999)))  # beyond Feb 9 cutoff
    data = load_rows(rows)
    forecast = nem_ml_data.build_next_day_demand_features(
        data, now=datetime(2026, 2, 10, 12, tzinfo=BRISBANE)
    )
    assert forecast["as_of_date"] == "2026-02-10"
    assert forecast["cutoff_date"] == "2026-02-09"
    assert forecast["forecast_date"] == "2026-02-11"
    assert forecast["last_observed_date"] == "2026-02-09"
    assert forecast["features"]["demand_at_cutoff"] == 139.0
    assert forecast["features"]["demand_6d_before_cutoff"] == 133.0
    assert forecast["features"]["demand_13d_before_cutoff"] == 126.0
    assert forecast["features"]["demand_27d_before_cutoff"] == 112.0


@pytest.mark.parametrize("offset", [0, 6, 13, 27])
def test_missing_cutoff_or_required_feature_returns_not_ready(offset):
    start = date(2026, 1, 1)
    cutoff = date(2026, 2, 9)
    missing_day = cutoff - timedelta(days=offset)
    rows = [
        observation(start + timedelta(days=i), Decimal(100 + i))
        for i in range(40)
        if start + timedelta(days=i) != missing_day
    ]
    data = load_rows(rows)
    with pytest.raises(nem_ml_data.NEMForecastNotReady):
        nem_ml_data.build_next_day_demand_features(
            data, now=datetime(2026, 2, 10, 12, tzinfo=BRISBANE)
        )


def test_payload_reports_not_ready_separately_when_cutoff_is_missing():
    from app.services.nem_ml_data import build_nem_prediction_payload

    start = date(2026, 1, 1)
    rows = [observation(start + timedelta(days=i), Decimal(100 + i)) for i in range(39)]
    payload = build_nem_prediction_payload(
        load_rows(rows), now=datetime(2026, 2, 10, 12, tzinfo=BRISBANE)
    )
    assert payload["forecast_status"] == "not_ready"
    assert payload["forecast"] is None
    assert payload["cutoff_date"] == "2026-02-09"
    assert payload["forecast_date"] == "2026-02-11"


def test_payload_excludes_training_targets_after_complete_data_cutoff():
    start = date(2026, 1, 1)
    rows = [observation(start + timedelta(days=index), Decimal(100 + index)) for index in range(41)]
    data = load_rows(rows)
    payload = nem_ml_data.build_nem_prediction_payload(
        data,
        now=datetime(2026, 2, 10, 12, tzinfo=ZoneInfo("Australia/Brisbane")),
    )

    assert payload["cutoff_date"] == "2026-02-09"
    assert payload["training_end"] == "2026-02-09"
    assert all(sample["target_date"] <= payload["cutoff_date"] for sample in payload["training_samples"])
    assert "2026-02-10" not in {sample["target_date"] for sample in payload["training_samples"]}
    assert payload["observation_end"] == "2026-02-09"
    assert payload["observation_count"] == 40
    without_current_day = nem_ml_data.build_nem_prediction_payload(
        load_rows(rows[:-1]),
        now=datetime(2026, 2, 10, 12, tzinfo=BRISBANE),
    )
    assert payload["data_fingerprint"] == without_current_day["data_fingerprint"]


def test_prediction_and_classification_share_the_same_forecast_context():
    from service_apps.prediction.schemas import NEMPredictionRequest
    from service_apps.classification.schemas import NEMClassificationRequest

    payload = nem_ml_data.build_nem_prediction_payload(
        continuous_data(40),
        now=datetime(2026, 2, 10, 12, tzinfo=BRISBANE),
    )
    prediction = NEMPredictionRequest.model_validate(payload)
    classification = NEMClassificationRequest.model_validate(payload)

    assert (prediction.as_of_date, prediction.cutoff_date, prediction.forecast_date) == (
        classification.as_of_date,
        classification.cutoff_date,
        classification.forecast_date,
    )
