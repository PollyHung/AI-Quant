"""Configuration loading for the Roostoo trading bot."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    roostoo_api_key: str
    roostoo_api_secret: str
    roostoo_base_url: str
    roostoo_pair: str
    poll_seconds: int
    max_position_usd: float
    min_cash_reserve_usd: float
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    short_window: int
    long_window: int
    cooldown_seconds: int
    dry_run: bool
    log_level: str
    request_timeout: int
    max_retries: int
    max_calls_per_minute: int


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise ValueError(f"Missing required environment variable: {name}")
    if value is None:
        raise ValueError(f"Missing environment variable with no default: {name}")
    return value


def _get_bool(name: str, default: str = "true") -> bool:
    raw = _get_env(name, default=default)
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _get_int(name: str, default: str) -> int:
    return int(_get_env(name, default=default))


def _get_float(name: str, default: str) -> float:
    return float(_get_env(name, default=default))


def load_settings() -> Settings:
    """Load and validate runtime settings from environment variables."""
    load_dotenv()

    settings = Settings(
        roostoo_api_key=_get_env("ROOSTOO_API_KEY", required=True),
        roostoo_api_secret=_get_env("ROOSTOO_API_SECRET", required=True),
        roostoo_base_url=_get_env("ROOSTOO_BASE_URL", "https://mock-api.roostoo.com").rstrip("/"),
        roostoo_pair=_get_env("ROOSTOO_PAIR", "BTCUSDT").upper(),
        poll_seconds=_get_int("POLL_SECONDS", "10"),
        max_position_usd=_get_float("MAX_POSITION_USD", "1000"),
        min_cash_reserve_usd=_get_float("MIN_CASH_RESERVE_USD", "100"),
        position_size_pct=_get_float("POSITION_SIZE_PCT", "0.25"),
        stop_loss_pct=_get_float("STOP_LOSS_PCT", "0.02"),
        take_profit_pct=_get_float("TAKE_PROFIT_PCT", "0.04"),
        short_window=_get_int("SHORT_WINDOW", "5"),
        long_window=_get_int("LONG_WINDOW", "20"),
        cooldown_seconds=_get_int("COOLDOWN_SECONDS", "30"),
        dry_run=_get_bool("DRY_RUN", "true"),
        log_level=_get_env("LOG_LEVEL", "INFO").upper(),
        request_timeout=_get_int("REQUEST_TIMEOUT", "10"),
        max_retries=_get_int("MAX_RETRIES", "4"),
        max_calls_per_minute=_get_int("MAX_CALLS_PER_MINUTE", "30"),
    )

    if settings.short_window <= 1:
        raise ValueError("SHORT_WINDOW must be > 1")
    if settings.long_window <= settings.short_window:
        raise ValueError("LONG_WINDOW must be greater than SHORT_WINDOW")
    if settings.poll_seconds < 1:
        raise ValueError("POLL_SECONDS must be >= 1")
    if not 0 < settings.position_size_pct <= 1:
        raise ValueError("POSITION_SIZE_PCT must be in (0, 1]")
    if settings.max_position_usd <= 0:
        raise ValueError("MAX_POSITION_USD must be > 0")
    if settings.stop_loss_pct <= 0:
        raise ValueError("STOP_LOSS_PCT must be > 0")
    if settings.take_profit_pct <= 0:
        raise ValueError("TAKE_PROFIT_PCT must be > 0")

    return settings
