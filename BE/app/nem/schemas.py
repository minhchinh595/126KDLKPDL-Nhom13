"""Validation and typed records for Open Electricity market responses."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


SUPPORTED_METRICS_BY_INTERVAL = {
    "5m": frozenset({"demand"}),
    "1d": frozenset(
        {
            "demand",
            "price",
            "demand_energy",
            "generation_renewable",
            "renewable_proportion",
        }
    ),
}
PRIMARY_GROUPINGS = frozenset({"network", "network_region"})

# This pairing is verified in the checked-in NEM JSON response. Other units are
# retained from the API response and must be supplied/verified by the caller.
VERIFIED_UNITS = {("demand", "5m"): "MW"}


class NEMResponseValidationError(ValueError):
    """The response does not match the supported Open Electricity schema."""


class NEMAPIRejected(NEMResponseValidationError):
    """The API returned a response with success=false."""


@dataclass(frozen=True, slots=True)
class NEMObservationRecord:
    network_code: str
    metric: str
    interval: str
    observed_at: datetime
    value: Decimal
    unit: str
    result: str
    grouping_type: str
    grouping_code: str

    def as_dict(self) -> dict[str, Any]:
        """Return fields compatible with NEMObservation, except dataset_id."""
        return {
            "network_code": self.network_code,
            "metric": self.metric,
            "interval": self.interval,
            "observed_at": self.observed_at,
            "value": self.value,
            "unit": self.unit,
            "result": self.result,
            "grouping_type": self.grouping_type,
            "grouping_code": self.grouping_code,
        }


def validate_request_spec(
    network_code: str,
    metrics: Sequence[str],
    interval: str,
    primary_grouping: str,
) -> tuple[str, ...]:
    """Validate supported network/metric/interval/grouping request values."""
    if not isinstance(network_code, str) or not network_code.strip():
        raise NEMResponseValidationError("network_code must be a non-empty string")
    if network_code != network_code.strip():
        raise NEMResponseValidationError("network_code cannot contain surrounding whitespace")
    if isinstance(metrics, (str, bytes)) or not isinstance(metrics, Sequence) or not metrics:
        raise NEMResponseValidationError("metrics must be a non-empty sequence of metric names")
    if not isinstance(interval, str) or interval not in SUPPORTED_METRICS_BY_INTERVAL:
        raise NEMResponseValidationError("interval must be 5m or 1d")
    if not isinstance(primary_grouping, str) or primary_grouping not in PRIMARY_GROUPINGS:
        raise NEMResponseValidationError("primary_grouping must be network or network_region")

    normalized: list[str] = []
    for metric in metrics:
        if not isinstance(metric, str) or not metric or metric.strip() != metric:
            raise NEMResponseValidationError("each metric must be a non-empty string")
        if metric not in SUPPORTED_METRICS_BY_INTERVAL[interval]:
            raise NEMResponseValidationError(
                f"metric {metric!r} is not supported for interval {interval!r}"
            )
        normalized.append(metric)
    return tuple(normalized)


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise NEMResponseValidationError(f"{field} must be a non-empty string")
    return value


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise NEMResponseValidationError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise NEMResponseValidationError("timestamp is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NEMResponseValidationError("timestamp must include a timezone offset")
    return parsed


def _parse_value(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise NEMResponseValidationError("observation value must be numeric")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise NEMResponseValidationError("observation value must be numeric") from exc
    if not parsed.is_finite():
        raise NEMResponseValidationError("observation value must be finite")
    return parsed


def _grouping_code(columns: Any, grouping_type: str) -> str:
    if not isinstance(columns, Mapping):
        raise NEMResponseValidationError("result columns must be an object")
    if grouping_type == "network":
        return ""

    # The API exposes region as a result column; network_region is a legacy
    # alias in some responses. Never infer a region from result.name.
    region = columns.get("region", columns.get("network_region"))
    return _required_string(region, "region grouping value")


def parse_response(
    payload: Any,
    *,
    expected_network_code: str | None = None,
    expected_metrics: Sequence[str] | None = None,
    expected_interval: str | None = None,
    primary_grouping: str = "network",
) -> list[NEMObservationRecord]:
    """Parse every point in an Open Electricity response without coercion of units or timezones."""
    if not isinstance(payload, Mapping):
        raise NEMResponseValidationError("response envelope must be an object")
    if payload.get("success") is not True:
        raise NEMAPIRejected("Open Electricity API reported success=false")

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise NEMResponseValidationError("response contains no metric series")
    if not isinstance(primary_grouping, str) or primary_grouping not in PRIMARY_GROUPINGS:
        raise NEMResponseValidationError("unsupported primary grouping")

    expected = set(expected_metrics or ())
    found_metrics: set[str] = set()
    records: list[NEMObservationRecord] = []

    for metric_series in data:
        if not isinstance(metric_series, Mapping):
            raise NEMResponseValidationError("metric series must be an object")
        network_code = _required_string(metric_series.get("network_code"), "network_code")
        metric = _required_string(metric_series.get("metric"), "metric")
        interval = _required_string(metric_series.get("interval"), "interval")
        unit = _required_string(metric_series.get("unit"), "unit")

        if expected_network_code is not None and network_code != expected_network_code:
            raise NEMResponseValidationError("response network_code does not match request")
        if expected_interval is not None and interval != expected_interval:
            raise NEMResponseValidationError("response interval does not match request")
        if interval not in SUPPORTED_METRICS_BY_INTERVAL:
            raise NEMResponseValidationError(f"unsupported response interval {interval!r}")
        if metric not in SUPPORTED_METRICS_BY_INTERVAL[interval]:
            raise NEMResponseValidationError(
                f"metric {metric!r} is not supported for interval {interval!r}"
            )
        known_unit = VERIFIED_UNITS.get((metric, interval))
        if known_unit is not None and unit != known_unit:
            raise NEMResponseValidationError(
                f"unit for {metric!r} at {interval!r} does not match the observed contract"
            )
        found_metrics.add(metric)

        groupings = metric_series.get("groupings", [])
        if not isinstance(groupings, list) or any(
            not isinstance(grouping, str) or not grouping for grouping in groupings
        ):
            raise NEMResponseValidationError("groupings must be a list of non-empty strings")
        if primary_grouping == "network" and groupings:
            raise NEMResponseValidationError("network response unexpectedly contains grouped series")

        results = metric_series.get("results")
        if not isinstance(results, list) or not results:
            raise NEMResponseValidationError(f"metric {metric!r} contains no result series")
        for result_series in results:
            if not isinstance(result_series, Mapping):
                raise NEMResponseValidationError("result series must be an object")
            result_name = _required_string(result_series.get("name"), "result name")
            columns = result_series.get("columns", {})
            grouping_code = _grouping_code(columns, primary_grouping)
            points = result_series.get("data")
            if not isinstance(points, list) or not points:
                raise NEMResponseValidationError(
                    f"result series {result_name!r} contains no observations"
                )

            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise NEMResponseValidationError(
                        f"result series {result_name!r} contains a malformed observation"
                    )

                observed_at = _parse_timestamp(point[0])

                # Open Electricity may return null when an interval has no observation.
                # Skip missing values instead of converting them to zero.
                if point[1] is None:
                    continue

                records.append(
                    NEMObservationRecord(
                        network_code=network_code,
                        metric=metric,
                        interval=interval,
                        observed_at=observed_at,
                        value=_parse_value(point[1]),
                        unit=unit,
                        result=result_name,
                        grouping_type=primary_grouping,
                        grouping_code=grouping_code,
                    )
                )

    missing_metrics = expected - found_metrics
    if missing_metrics:
        raise NEMResponseValidationError(
            "response is missing requested metric series: " + ", ".join(sorted(missing_metrics))
        )
    if not records:
        raise NEMResponseValidationError("response contains no observations")
    return records
