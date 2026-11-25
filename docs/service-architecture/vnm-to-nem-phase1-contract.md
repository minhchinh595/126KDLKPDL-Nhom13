# VNM-to-NEM Backend migration — Phase 1 contracts

Phase 1 makes Open Electricity NEM the source for the public Electricity,
Dashboard, descriptive Analysis, and demand Report read APIs. These public
contracts changed intentionally; the Frontend still expects the older VNM
monthly schema and needs a later coordinated update.

## Migrated public routes

- `GET /api/electricity/observations`: metric/interval and optional aware
  `start_at`/`end_at`, with page pagination. A 5-minute query requires both
  bounds and is limited to seven days.
- `GET /api/electricity/demand` and its statistics/detail/export routes remain
  at their former paths, but now return NEM demand (`1d` by default) and no
  longer expose fabricated `iso3`, country, month, or TWh fields.
- `GET /api/dashboard/overview` reports NEM observation count, daily-demand
  KPIs, latest daily price and renewable proportion, dataset status, and
  Brisbane-local timezone. Month-over-month comparison was removed.
- `GET /api/analysis/{summary,trend,seasonality,correlation,distribution}` now
  consume NEM daily network observations and publish typed NEM response schemas.
  Trend accepts a daily metric and `view=day|week|month`;
  distribution accepts metric and interval. `/api/analysis/scatter` returns
  paired daily points.
- `/api/reports/analysis` and demand export use NEM observations. Model-run
  report routes remain unchanged.

All migrated read routes retain Analyst authentication. They resolve the NEM
dataset by exact name and source and return 503 if missing or ambiguous; VNM is
never a fallback. Existing VNM ingestion, prediction, classification, and
clustering code remains temporarily active/legacy and is scheduled for Phase 2.
No database schema or stored VNM data changed in Phase 1.

## Aggregation and data limits

Daily demand, renewable generation, price, energy, and proportion retain their
source interval values for summary/distribution/correlation. Trend aggregates
daily demand and renewable generation rates by the mean of observed daily
values and returns calendar-day coverage, preserving missing days as null;
daily intra-day coverage is not available. Demand energy is summed in MWh.
Weekly/monthly prices use same-day demand energy as the weight and report the
number of weighted days. Renewable proportion is not summed or resampled and
returns null for week/month views because a valid aggregate denominator is
unavailable.
Correlation and scatter align by the same Australia/Brisbane calendar date.
No missing observation is filled.
