"""Logging setup and structured event helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


class _PairFilter(logging.Filter):
    def __init__(self, pair: str) -> None:
        super().__init__()
        self.pair = pair

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "pair"):
            record.pair = self.pair
        return True


def build_logger(name: str, level: str, pair: str) -> logging.Logger:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | pair=%(pair)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(logs_dir / "bot.log")
    file_handler.setFormatter(formatter)

    pair_filter = _PairFilter(pair)
    logger.addFilter(pair_filter)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def log_event(logger: logging.Logger, level: int, event: str, **kwargs: Any) -> None:
    kv = " ".join(f"{k}={v}" for k, v in kwargs.items())
    message = f"event={event}"
    if kv:
        message = f"{message} {kv}"
    logger.log(level, message)
