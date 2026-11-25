"""Standalone, testable Open Electricity NEM ingestion worker."""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from app.db.database import get_session_factory
from app.nem.client import (
    DEFAULT_API_BASE_URL,
    NEMConfigurationError,
    NEMConnectionError,
    NEMHTTPError,
    NEMTimeoutError,
    OpenElectricityClient,
)
from app.nem.schemas import NEMObservationRecord
from app.services.nem_import import import_nem_observations


# Open Electricity documents the NEM network clock as UTC+10. Brisbane is the
# IANA zone that represents AEST year-round without applying Sydney daylight
# saving to market timestamps.
NEM_TIMEZONE = ZoneInfo("Australia/Brisbane")
DAILY_METRICS = (
    "demand",
    "price",
    "demand_energy",
    "generation_renewable",
    "renewable_proportion",
)
LOGGER = logging.getLogger("app.nem.worker")
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 8.0


class WorkerConfigurationError(ValueError):
    """Worker configuration is missing or invalid."""


class PollAlreadyRunning(RuntimeError):
    """Another poll currently owns the worker's poll lock."""


def _positive_float(name: str, value: str | None, default: float) -> float:
    raw = str(default) if value is None else value
    try:
        parsed = float(raw)
    except (TypeError, ValueError, OverflowError):
        raise WorkerConfigurationError(f"{name} must be a positive finite number") from None
    if not math.isfinite(parsed) or parsed <= 0:
        raise WorkerConfigurationError(f"{name} must be a positive finite number")
    return parsed


def _positive_int(name: str, value: str | None, default: int) -> int:
    raw = str(default) if value is None else value
    try:
        parsed = int(raw)
    except (TypeError, ValueError, OverflowError):
        raise WorkerConfigurationError(f"{name} must be a positive integer") from None
    if parsed <= 0 or str(parsed) != raw.strip():
        raise WorkerConfigurationError(f"{name} must be a positive integer")
    return parsed


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_API_BASE_URL
    timeout_seconds: float = 30.0
    five_minute_poll_seconds: float = 300.0
    daily_poll_seconds: float = 86400.0
    five_minute_lookback_minutes: int = 30
    daily_lookback_days: int = 3

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        api_key = os.getenv("OPEN_ELECTRICITY_API_KEY", "").strip()
        if not api_key:
            raise WorkerConfigurationError("OPEN_ELECTRICITY_API_KEY is not configured")

        # The current client uses API_BASE_URL; accept the worker-specific name
        # from the deployment contract first, then the existing client name.
        base_url = (
            os.getenv("OPEN_ELECTRICITY_BASE_URL")
            or os.getenv("OPEN_ELECTRICITY_API_BASE_URL")
            or DEFAULT_API_BASE_URL
        ).strip()
        if not base_url:
            raise WorkerConfigurationError("OPEN_ELECTRICITY_BASE_URL is not configured")

        return cls(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=_positive_float(
                "OPEN_ELECTRICITY_TIMEOUT_SECONDS",
                os.getenv("OPEN_ELECTRICITY_TIMEOUT_SECONDS"),
                30.0,
            ),
            five_minute_poll_seconds=_positive_float(
                "NEM_5M_POLL_SECONDS", os.getenv("NEM_5M_POLL_SECONDS"), 300.0
            ),
            daily_poll_seconds=_positive_float(
                "NEM_DAILY_POLL_SECONDS", os.getenv("NEM_DAILY_POLL_SECONDS"), 86400.0
            ),
            five_minute_lookback_minutes=_positive_int(
                "NEM_5M_LOOKBACK_MINUTES",
                os.getenv("NEM_5M_LOOKBACK_MINUTES"),
                30,
            ),
            daily_lookback_days=_positive_int(
                "NEM_DAILY_LOOKBACK_DAYS",
                os.getenv("NEM_DAILY_LOOKBACK_DAYS"),
                3,
            ),
        )


def _default_session_factory():
    return get_session_factory()()


def _is_transient(error: Exception) -> bool:
    if isinstance(error, (NEMTimeoutError, NEMConnectionError, TimeoutError, ConnectionError)):
        return True
    return isinstance(error, NEMHTTPError) and (
        error.status_code == 408 or error.status_code == 429 or error.status_code >= 500
    )


class NEMIngestionWorker:
    """Fetch and persist bounded NEM windows without overlapping polls."""

    def __init__(
        self,
        config: WorkerConfig | None = None,
        *,
        client=None,
        session_factory: Callable | None = None,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or WorkerConfig.from_env()
        self.client = client or OpenElectricityClient(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout_seconds=self.config.timeout_seconds,
        )
        self.session_factory = session_factory or _default_session_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep
        self.logger = logger or LOGGER
        self._poll_lock = threading.Lock()
        self._next_five_minute: datetime | None = None
        self._next_daily: datetime | None = None

    def _now(self) -> datetime:
        current = self.clock()
        if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
            raise WorkerConfigurationError("worker clock must return a timezone-aware datetime")
        return current.astimezone(timezone.utc)

    def _request(
        self,
        metrics: Sequence[str],
        interval: str,
        date_start: datetime,
        date_end: datetime,
    ) -> list[NEMObservationRecord]:
        # Enforce the no-request-without-key rule even when an injected client
        # does not perform its own environment validation.
        if not self.config.api_key.strip():
            raise WorkerConfigurationError("OPEN_ELECTRICITY_API_KEY is not configured")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self.client.get_observations(
                    "NEM", metrics, interval, date_start, date_end, "network"
                )
            except Exception as exc:
                if not _is_transient(exc) or attempt == MAX_ATTEMPTS:
                    raise
                delay = min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_MAX_SECONDS)
                self.logger.warning(
                    "NEM %s poll request failed transiently (attempt %d/%d); retrying in %.1fs",
                    interval,
                    attempt,
                    MAX_ATTEMPTS,
                    delay,
                )
                self.sleep(delay)
        raise AssertionError("unreachable retry loop")

    def _run_poll(self, interval: str, metrics: Sequence[str], start: datetime, end: datetime):
        if not self._poll_lock.acquire(blocking=False):
            self.logger.info("Skipping NEM %s poll because another poll is active", interval)
            return None
        try:
            records = self._request(metrics, interval, start, end)
            if not records:
                self.logger.info("NEM %s poll returned no observations; nothing imported", interval)
                return None
            try:
                with self.session_factory() as db:
                    history = import_nem_observations(db, records)
                self.logger.info(
                    "NEM %s poll completed: rows=%d inserted=%d updated=%d skipped=%d",
                    interval,
                    history.rows_read,
                    history.inserted_count,
                    history.updated_count,
                    history.skipped_count,
                )
                return history
            except Exception as exc:
                self.logger.error(
                    "NEM %s persistence failed (%s)", interval, type(exc).__name__
                )
                raise
        finally:
            self._poll_lock.release()

    @staticmethod
    def _floor_five_minutes(value: datetime) -> datetime:
        epoch = value.timestamp()
        aligned_epoch = math.floor(epoch / 300) * 300
        return datetime.fromtimestamp(aligned_epoch, timezone.utc).astimezone(NEM_TIMEZONE)

    def poll_5m(self):
        """Fetch demand for an aligned recent [start, end) window."""
        now = self._now()
        end = self._floor_five_minutes(now)
        start = self._floor_five_minutes(
            now - timedelta(minutes=self.config.five_minute_lookback_minutes)
        )
        if start >= end:
            self.logger.info("NEM 5m poll window is empty; nothing requested")
            return None
        return self._run_poll("5m", ("demand",), start, end)

    def poll_daily(self):
        """Fetch completed NEM-local calendar days, excluding today's partial day."""
        now_local = self._now().astimezone(NEM_TIMEZONE)
        end = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=NEM_TIMEZONE)
        start_date = now_local.date() - timedelta(days=self.config.daily_lookback_days)
        start = datetime.combine(start_date, datetime.min.time(), tzinfo=NEM_TIMEZONE)
        if start >= end:
            self.logger.info("NEM daily poll window is empty; nothing requested")
            return None
        return self._run_poll("1d", DAILY_METRICS, start, end)

    def run_iteration(self) -> dict[str, bool]:
        """Run jobs due at the current clock instant; first iteration runs both."""
        now = self._now()
        ran = {"5m": False, "1d": False}
        if self._next_five_minute is None or now >= self._next_five_minute:
            ran["5m"] = True
            self._next_five_minute = now + timedelta(
                seconds=self.config.five_minute_poll_seconds
            )
            self._run_iteration_job("5m", self.poll_5m)
        if self._next_daily is None or now >= self._next_daily:
            ran["1d"] = True
            self._next_daily = now + timedelta(seconds=self.config.daily_poll_seconds)
            self._run_iteration_job("1d", self.poll_daily)
        return ran

    def _run_iteration_job(self, name: str, job: Callable[[], object]) -> None:
        try:
            job()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            self.logger.error("NEM %s poll failed (%s)", name, type(exc).__name__)

    def run(self, *, stop_event: threading.Event | None = None, idle_sleep_seconds: float = 1.0) -> None:
        """Continuously run due jobs; stop cleanly on signal-like exceptions."""
        if not math.isfinite(idle_sleep_seconds) or idle_sleep_seconds <= 0:
            raise WorkerConfigurationError("idle_sleep_seconds must be positive and finite")
        stop_event = stop_event or threading.Event()
        try:
            while not stop_event.is_set():
                self.run_iteration()
                if not stop_event.is_set():
                    self.sleep(idle_sleep_seconds)
        except (KeyboardInterrupt, SystemExit):
            self.logger.info("NEM ingestion worker stopping")


def main() -> None:
    """Process entry point: ``python -m app.nem.worker``."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    try:
        worker = NEMIngestionWorker()
    except (WorkerConfigurationError, NEMConfigurationError):
        LOGGER.error("NEM ingestion worker configuration is invalid or incomplete")
        raise SystemExit(2) from None
    worker.run()


if __name__ == "__main__":
    main()
