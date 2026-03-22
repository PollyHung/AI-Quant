"""Main event loop for the Roostoo autonomous trading bot."""

from __future__ import annotations

import logging
import time
from typing import Any

from api_client import APIError, RoostooClient
from config import Settings, load_settings
from execution import ExecutionEngine
from logger import build_logger, log_event
from risk import PositionState, RiskManager
from strategy import MovingAverageMomentumStrategy
from utils import normalize_pair, safe_float, split_pair


def _extract_pair_ticker(payload: dict[str, Any], pair: str) -> dict[str, Any]:
    if payload.get("pair") == pair:
        return payload

    for key in ("data", "result", "tickers"):
        value = payload.get(key)
        if isinstance(value, list):
            for row in value:
                row_pair = normalize_pair(str(row.get("pair", row.get("symbol", ""))))
                if row_pair == normalize_pair(pair):
                    return row
        elif isinstance(value, dict):
            row_pair = normalize_pair(str(value.get("pair", value.get("symbol", ""))))
            if row_pair == normalize_pair(pair):
                return value

    return payload


def _extract_last_price(ticker: dict[str, Any]) -> float:
    for key in ("last", "lastPrice", "price", "close", "markPrice"):
        if key in ticker:
            return safe_float(ticker[key])
    return 0.0


def _extract_balances(balance_payload: dict[str, Any], base_asset: str, quote_asset: str) -> tuple[float, float]:
    entries: list[dict[str, Any]] = []

    if isinstance(balance_payload.get("balances"), list):
        entries = balance_payload["balances"]
    elif isinstance(balance_payload.get("data"), list):
        entries = balance_payload["data"]

    base_balance = 0.0
    quote_balance = 0.0

    for row in entries:
        asset = str(row.get("asset", row.get("coin", row.get("currency", "")))).upper()
        free = safe_float(row.get("free", row.get("available", row.get("balance", 0.0))))
        if asset == base_asset:
            base_balance = free
        elif asset == quote_asset:
            quote_balance = free

    return base_balance, quote_balance


def _portfolio_value(quote_balance: float, base_balance: float, price: float) -> float:
    return quote_balance + (base_balance * price)


def _validate_runtime_budget(settings: Settings) -> None:
    estimated_calls_per_loop = 3
    estimated_calls_per_min = (60 / settings.poll_seconds) * estimated_calls_per_loop
    if estimated_calls_per_min > settings.max_calls_per_minute:
        raise ValueError(
            "POLL_SECONDS too low for safe request volume. "
            f"Estimated {estimated_calls_per_min:.1f} calls/min > limit {settings.max_calls_per_minute}."
        )


def main() -> None:
    settings = load_settings()
    _validate_runtime_budget(settings)

    logger = build_logger("roostoo_bot", settings.log_level, settings.roostoo_pair)

    client = RoostooClient(
        base_url=settings.roostoo_base_url,
        api_key=settings.roostoo_api_key,
        api_secret=settings.roostoo_api_secret,
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
        max_calls_per_minute=settings.max_calls_per_minute,
    )

    strategy = MovingAverageMomentumStrategy(settings.short_window, settings.long_window)
    risk = RiskManager(
        max_position_usd=settings.max_position_usd,
        min_cash_reserve_usd=settings.min_cash_reserve_usd,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
        cooldown_seconds=settings.cooldown_seconds,
    )

    position = PositionState()

    server_time = client.get_server_time()
    exchange_info = client.get_exchange_info()

    constraints = risk.parse_pair_constraints(exchange_info, settings.roostoo_pair)
    if not constraints.found:
        raise RuntimeError(f"Configured pair not found in exchangeInfo: {settings.roostoo_pair}")
    if not constraints.tradable:
        raise RuntimeError(f"Configured pair is not tradable: {settings.roostoo_pair}")

    execution = ExecutionEngine(
        client=client,
        risk=risk,
        logger=logger,
        pair=settings.roostoo_pair,
        position_size_pct=settings.position_size_pct,
        dry_run=settings.dry_run,
        constraints=constraints,
    )

    log_event(
        logger,
        logging.INFO,
        "bot_start",
        pair=settings.roostoo_pair,
        dry_run=settings.dry_run,
        server_time=server_time,
        constraints=constraints,
    )

    base_asset, quote_asset = split_pair(settings.roostoo_pair)

    while True:
        try:
            ticker_payload = client.get_ticker(settings.roostoo_pair)
            ticker = _extract_pair_ticker(ticker_payload, settings.roostoo_pair)
            last_price = _extract_last_price(ticker)

            if last_price <= 0:
                log_event(logger, logging.WARNING, "ticker_invalid", payload=ticker_payload)
                time.sleep(settings.poll_seconds)
                continue

            strategy.update_price(last_price)
            signal = strategy.generate_signal()

            balance_payload = client.get_balance()
            base_balance, quote_balance = _extract_balances(balance_payload, base_asset, quote_asset)

            force_exit, force_reason = risk.check_stop_or_take_profit(position, last_price)
            action = "SELL" if force_exit else signal.action
            reason = force_reason if force_exit else signal.reason

            result = execution.maybe_execute(
                action=action,
                signal_reason=reason,
                last_price=last_price,
                quote_balance=quote_balance,
                base_balance=base_balance,
                position=position,
                max_position_usd=settings.max_position_usd,
            )

            portfolio_value = _portfolio_value(quote_balance, base_balance, last_price)
            log_event(
                logger,
                logging.INFO,
                "loop_status",
                price=f"{last_price:.6f}",
                signal=signal.action,
                signal_reason=signal.reason,
                exec_action=result.action,
                exec_reason=result.reason,
                qty=f"{result.quantity:.8f}",
                order_id=result.order_id,
                short_ma=f"{signal.short_ma:.6f}",
                long_ma=f"{signal.long_ma:.6f}",
                momentum=f"{signal.momentum:.6f}",
                base_balance=f"{base_balance:.8f}",
                quote_balance=f"{quote_balance:.2f}",
                portfolio_value=f"{portfolio_value:.2f}",
            )

        except APIError as exc:
            log_event(logger, logging.ERROR, "api_failure", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            log_event(logger, logging.ERROR, "loop_exception", error=str(exc))

        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
