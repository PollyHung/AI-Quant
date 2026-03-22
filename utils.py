"""Utility helpers used across the bot."""

from __future__ import annotations

import math
import time
from typing import Any


def now_ms() -> int:
    """Current UNIX timestamp in milliseconds."""
    return int(time.time() * 1000)


def safe_float(value: Any, default: float = 0.0) -> float:
    """Best effort numeric conversion."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def floor_to_precision(value: float, precision: int) -> float:
    """Round down to exchange amount precision."""
    if precision < 0:
        raise ValueError("precision must be >= 0")
    factor = 10 ** precision
    return math.floor(value * factor) / factor


def normalize_pair(pair: str) -> str:
    return pair.replace("/", "").replace("-", "").upper()


def split_pair(pair: str) -> tuple[str, str]:
    """Attempt to split pair into base and quote assets."""
    normalized = normalize_pair(pair)
    common_quotes = ("USDT", "USDC", "USD", "BTC", "ETH")
    for quote in common_quotes:
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)], quote
    return normalized[:-4], normalized[-4:]


def extract_order_id(resp: dict[str, Any]) -> str:
    for key in ("orderId", "order_id", "id"):
        if key in resp:
            return str(resp[key])
    return ""
