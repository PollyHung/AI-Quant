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
    trailing_stop_pct: float
    min_hold_seconds: int
    strategy_mode: str
    dip_step_pct: float
    dip_rebound_pct: float
    dip_lookback: int
    dip_max_tranches: int
    short_window: int
    long_window: int
    cooldown_seconds: int
    dry_run: bool
    log_level: str
    request_timeout: int
    max_retries: int
    max_calls_per_minute: int
    adaptive_enabled: bool
    adaptive_reevaluate_loops: int
    adaptive_min_short_window: int
    adaptive_max_short_window: int
    adaptive_min_long_window: int
    adaptive_max_long_window: int
    adaptive_min_position_size_pct: float
    adaptive_max_position_size_pct: float
    adaptive_drawdown_threshold: float
    adaptive_loss_streak_threshold: int
    adaptive_history_window: int


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
        roostoo_pair=_get_env("ROOSTOO_PAIR", "BTC/USD").upper(),
        poll_seconds=_get_int("POLL_SECONDS", "10"),
        max_position_usd=_get_float("MAX_POSITION_USD", "1000"),
        min_cash_reserve_usd=_get_float("MIN_CASH_RESERVE_USD", "100"),
        position_size_pct=_get_float("POSITION_SIZE_PCT", "0.25"),
        stop_loss_pct=_get_float("STOP_LOSS_PCT", "0.02"),
        take_profit_pct=_get_float("TAKE_PROFIT_PCT", "0.04"),
        trailing_stop_pct=_get_float("TRAILING_STOP_PCT", "0.01"),
        min_hold_seconds=_get_int("MIN_HOLD_SECONDS", "180"),
        strategy_mode=_get_env("STRATEGY_MODE", "dip_ladder").strip().lower(),
        dip_step_pct=_get_float("DIP_STEP_PCT", "0.006"),
        dip_rebound_pct=_get_float("DIP_REBOUND_PCT", "0.0015"),
        dip_lookback=_get_int("DIP_LOOKBACK", "18"),
        dip_max_tranches=_get_int("DIP_MAX_TRANCHES", "4"),
        short_window=_get_int("SHORT_WINDOW", "5"),
        long_window=_get_int("LONG_WINDOW", "20"),
        cooldown_seconds=_get_int("COOLDOWN_SECONDS", "30"),
        dry_run=_get_bool("DRY_RUN", "true"),
        log_level=_get_env("LOG_LEVEL", "INFO").upper(),
        request_timeout=_get_int("REQUEST_TIMEOUT", "10"),
        max_retries=_get_int("MAX_RETRIES", "4"),
        max_calls_per_minute=_get_int("MAX_CALLS_PER_MINUTE", "30"),
        adaptive_enabled=_get_bool("ADAPTIVE_ENABLED", "true"),
        adaptive_reevaluate_loops=_get_int("ADAPTIVE_REEVALUATE_LOOPS", "18"),
        adaptive_min_short_window=_get_int("ADAPTIVE_MIN_SHORT_WINDOW", "3"),
        adaptive_max_short_window=_get_int("ADAPTIVE_MAX_SHORT_WINDOW", "20"),
        adaptive_min_long_window=_get_int("ADAPTIVE_MIN_LONG_WINDOW", "10"),
        adaptive_max_long_window=_get_int("ADAPTIVE_MAX_LONG_WINDOW", "60"),
        adaptive_min_position_size_pct=_get_float("ADAPTIVE_MIN_POSITION_SIZE_PCT", "0.10"),
        adaptive_max_position_size_pct=_get_float("ADAPTIVE_MAX_POSITION_SIZE_PCT", "0.50"),
        adaptive_drawdown_threshold=_get_float("ADAPTIVE_DRAWDOWN_THRESHOLD", "0.05"),
        adaptive_loss_streak_threshold=_get_int("ADAPTIVE_LOSS_STREAK_THRESHOLD", "3"),
        adaptive_history_window=_get_int("ADAPTIVE_HISTORY_WINDOW", "36"),
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
    if settings.trailing_stop_pct <= 0:
        raise ValueError("TRAILING_STOP_PCT must be > 0")
    if settings.min_hold_seconds < 0:
        raise ValueError("MIN_HOLD_SECONDS must be >= 0")
    if settings.strategy_mode not in {"ma_momentum", "dip_ladder"}:
        raise ValueError("STRATEGY_MODE must be one of: ma_momentum, dip_ladder")
    if settings.dip_step_pct <= 0:
        raise ValueError("DIP_STEP_PCT must be > 0")
    if settings.dip_rebound_pct < 0:
        raise ValueError("DIP_REBOUND_PCT must be >= 0")
    if settings.dip_lookback < 5:
        raise ValueError("DIP_LOOKBACK must be >= 5")
    if settings.dip_max_tranches < 1:
        raise ValueError("DIP_MAX_TRANCHES must be >= 1")
    if settings.adaptive_reevaluate_loops < 1:
        raise ValueError("ADAPTIVE_REEVALUATE_LOOPS must be >= 1")
    if settings.adaptive_min_short_window < 2:
        raise ValueError("ADAPTIVE_MIN_SHORT_WINDOW must be >= 2")
    if settings.adaptive_max_short_window < settings.adaptive_min_short_window:
        raise ValueError("ADAPTIVE_MAX_SHORT_WINDOW must be >= ADAPTIVE_MIN_SHORT_WINDOW")
    if settings.adaptive_min_long_window <= settings.adaptive_min_short_window:
        raise ValueError("ADAPTIVE_MIN_LONG_WINDOW must be > ADAPTIVE_MIN_SHORT_WINDOW")
    if settings.adaptive_max_long_window < settings.adaptive_min_long_window:
        raise ValueError("ADAPTIVE_MAX_LONG_WINDOW must be >= ADAPTIVE_MIN_LONG_WINDOW")
    if not 0 < settings.adaptive_min_position_size_pct <= 1:
        raise ValueError("ADAPTIVE_MIN_POSITION_SIZE_PCT must be in (0, 1]")
    if not 0 < settings.adaptive_max_position_size_pct <= 1:
        raise ValueError("ADAPTIVE_MAX_POSITION_SIZE_PCT must be in (0, 1]")
    if settings.adaptive_max_position_size_pct < settings.adaptive_min_position_size_pct:
        raise ValueError("ADAPTIVE_MAX_POSITION_SIZE_PCT must be >= ADAPTIVE_MIN_POSITION_SIZE_PCT")
    if settings.adaptive_drawdown_threshold <= 0:
        raise ValueError("ADAPTIVE_DRAWDOWN_THRESHOLD must be > 0")
    if settings.adaptive_loss_streak_threshold < 1:
        raise ValueError("ADAPTIVE_LOSS_STREAK_THRESHOLD must be >= 1")
    if settings.adaptive_history_window < 5:
        raise ValueError("ADAPTIVE_HISTORY_WINDOW must be >= 5")

    return settings
