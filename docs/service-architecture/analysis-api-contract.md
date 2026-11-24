# Analysis API contract baseline

This document records the public contract implemented by `BE/app/api/routes/analysis.py` and `BE/app/schemas/analysis.py` before the service extraction. All public routes use HTTP `GET` and are mounted under `/api` by `BE/app/main.py`.

## Authentication and shared behavior

- All routes require the `electricity_access_token` HttpOnly JWT cookie.
- `require_analyst` permits both `analyst` and `admin`. Missing, invalid, expired, inactive-account tokens return `401`; an authenticated role outside the allowed set returns `403`.
- Query parameters `start_month` and `end_month` are optional `YYYY-MM` strings. The Backend filters rows to `VNM`, `demand`, `fuel IS NULL`, `TWh` and orders ascending by month before analysis.
- `start_month > end_month`, malformed month strings, invalid endpoint-specific bounds return `422`.
- PostgreSQL query failures return `503` with `Electricity data is unavailable in PostgreSQL`.
- Empty source ranges return successful empty/nullable analytics, not fabricated observations.

## Endpoint contracts

| Method and URL | Query parameters | Successful response |
|---|---|---|
| `GET /api/analysis/summary` | `start_month?`, `end_month?` | `{unit, start_month, end_month, count, mean, median, min, max}`. `unit` is `TWh`; boundaries and statistics are `null` when there are no rows; numeric statistics are rounded to 4 decimals. |
| `GET /api/analysis/trend` | `start_month?`, `end_month?`, `window_months=12` (2–36) | `{unit, window_months, method, records[]}`. Each record is `{month, value, trend}`; trend is a trailing rolling mean and can be `null` until a complete window exists. |
| `GET /api/analysis/seasonality` | `start_month?`, `end_month?` | `{unit, method, records[12]}`. Each calendar-month item is `{month_number, count, mean, median, min, max}`; empty calendar months have null statistics. |
| `GET /api/analysis/correlation` | `start_month?`, `end_month?` | `{unit, method, features[], matrix, pair_counts}`. Features are `demand`, `previous_month`, `previous_year`; coefficients can be null when fewer than 3 pairs exist or variance is zero. |
| `GET /api/analysis/distribution` | `start_month?`, `end_month?`, `bins=10` (2–50) | `{unit, count, bins[]}` where each bin is `{start, end, count}`. Empty input returns an empty bins list; constant input returns one bin. |

All successful responses are validated by the existing Pydantic response models in `BE/app/schemas/analysis.py`: `SummaryResponse`, `TrendResponse`, `SeasonalityResponse`, `CorrelationResponse` and `DistributionResponse`.

## Test coverage found before extraction

- `BE/tests/test_electricity.py::test_openapi_contains_preserved_and_added_routes` asserts that the five public paths exist in OpenAPI. It does not assert query parameters, response fields or error codes.
- `BE/tests/test_api.py::test_unauthenticated_routes_reject_requests` checks that the summary route returns `401` without a session.
- `BE/tests/test_api.py::test_dashboard_analysis_model_runs_and_reports` checks summary count and successful responses from all five Analysis endpoints and the report Analysis endpoint. It does not check the exact response models or service outage behavior.
- Role behavior is covered more broadly by `test_analyst_can_read_but_cannot_manage_or_run`; Analysis routes share `require_analyst` at the router level.

## Contract after extraction

The public method, URL, authentication, role, query names/bounds and response schemas remain unchanged. Gateway validation and PostgreSQL filtering remain in the existing router. It sends the resulting monthly records to the private Analysis Service over HTTP. A new infrastructure error is possible: if Analysis Service is unconfigured, times out, is unreachable, or returns an unusable response, the Gateway returns `503` with the non-sensitive detail `Analysis service is unavailable`. The internal URL and credential are never included in that public error.

Distribution is included in the service boundary as well, so none of the existing public Analysis endpoints continue to compute analytics locally in the Gateway.
