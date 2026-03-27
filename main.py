"""Main event loop for the Roostoo autonomous trading bot."""

from __future__ import annotations

import logging
import time
from typing import Any

from adaptive import AdaptiveConfig, AdaptiveController
from api_client import APIError, RoostooClient
from config import Settings, load_settings
from execution import ExecutionEngine
from logger import build_logger, log_event
from risk import PositionState, RiskManager
from strategy import DipLadderStrategy, MovingAverageMomentumStrategy
from utils import normalize_pair, safe_float, split_pair


def _extract_pair_ticker(payload: dict[str, Any], pair: str) -> dict[str, Any]:
    if payload.get("pair") == pair:
        return payload

    data = payload.get("Data")
    if isinstance(data, dict):
        # Roostoo format: {"Data": {"XRP/USD": {...}}}
        for k, v in data.items():
            if normalize_pair(str(k)) == normalize_pair(pair) and isinstance(v, dict):
                return v

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
    for key in ("last", "lastPrice", "LastPrice", "price", "close", "markPrice"):
        if key in ticker:
            return safe_float(ticker[key])
    return 0.0


def _extract_balances(balance_payload: dict[str, Any], base_asset: str, quote_asset: str) -> tuple[float, float]:
    entries: list[dict[str, Any]] = []
    wallet = balance_payload.get("SpotWallet")
    if isinstance(wallet, dict):
        base = wallet.get(base_asset, {})
        quote = wallet.get(quote_asset, {})
        base_balance = safe_float(base.get("Free", base.get("free", 0.0)))
        quote_balance = safe_float(quote.get("Free", quote.get("free", 0.0)))
        return base_balance, quote_balance

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
    estimated_calls_per_loop = 4
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

    if settings.strategy_mode == "dip_ladder":
        strategy = DipLadderStrategy(
            dip_step_pct=settings.dip_step_pct,
            rebound_pct=settings.dip_rebound_pct,
            lookback=settings.dip_lookback,
            max_tranches=settings.dip_max_tranches,
        )
    else:
        strategy = MovingAverageMomentumStrategy(settings.short_window, settings.long_window)
    risk = RiskManager(
        max_position_usd=settings.max_position_usd,
        min_cash_reserve_usd=settings.min_cash_reserve_usd,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
        trailing_stop_pct=settings.trailing_stop_pct,
        min_hold_seconds=settings.min_hold_seconds,
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
    adaptive = AdaptiveController(
        config=AdaptiveConfig(
            enabled=settings.adaptive_enabled,
            reevaluate_loops=settings.adaptive_reevaluate_loops,
            min_short_window=settings.adaptive_min_short_window,
            max_short_window=settings.adaptive_max_short_window,
            min_long_window=settings.adaptive_min_long_window,
            max_long_window=settings.adaptive_max_long_window,
            min_position_size_pct=settings.adaptive_min_position_size_pct,
            max_position_size_pct=settings.adaptive_max_position_size_pct,
            drawdown_threshold=settings.adaptive_drawdown_threshold,
            loss_streak_threshold=settings.adaptive_loss_streak_threshold,
            history_window=settings.adaptive_history_window,
        ),
        initial_short=settings.short_window,
        initial_long=settings.long_window,
        initial_pos_pct=settings.position_size_pct,
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
            signal = strategy.generate_signal(position=position)

            balance_payload = client.get_balance()
            base_balance, quote_balance = _extract_balances(balance_payload, base_asset, quote_asset)

            force_exit, force_reason = risk.check_stop_or_take_profit(position, last_price)
            if force_exit:
                action = "SELL"
                reason = force_reason
            elif signal.action == "BUY":
                action = "BUY"
                reason = signal.reason
            else:
                action = "HOLD"
                reason = "hold_until_exit_model"

            pre_qty = position.quantity
            pre_avg_price = position.avg_entry_price
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
            adaptive.on_portfolio_value(portfolio_value)

            if result.executed and result.action == "SELL" and pre_qty > 0 and pre_avg_price > 0 and result.quantity > 0:
                realized_pnl = (last_price - pre_avg_price) * result.quantity
                adaptive.on_realized_trade_pnl(realized_pnl)
                log_event(
                    logger,
                    logging.INFO,
                    "trade_outcome",
                    side="SELL",
                    pnl=f"{realized_pnl:.2f}",
                    outcome="win" if realized_pnl > 0 else "loss",
                    qty=f"{result.quantity:.8f}",
                    entry=f"{pre_avg_price:.6f}",
                    exit=f"{last_price:.6f}",
                )

            adapt = adaptive.maybe_reconfigure()
            if adapt.changed:
                if hasattr(strategy, "reconfigure"):
                    strategy.reconfigure(adapt.new_short_window, adapt.new_long_window)
                execution.position_size_pct = adapt.new_position_size_pct
                log_event(
                    logger,
                    logging.INFO,
                    "adaptive_reconfigure",
                    reason=adapt.reason,
                    short_window=adapt.new_short_window,
                    long_window=adapt.new_long_window,
                    position_size_pct=f"{adapt.new_position_size_pct:.4f}",
                    rolling_return=f"{adapt.rolling_return:.5f}",
                    total_return=f"{adapt.total_return:.5f}",
                    drawdown=f"{adapt.drawdown:.5f}",
                    win_rate=f"{adapt.win_rate:.4f}",
                )

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
                rolling_return=f"{adapt.rolling_return:.5f}",
                total_return=f"{adapt.total_return:.5f}",
                drawdown=f"{adapt.drawdown:.5f}",
                win_rate=f"{adapt.win_rate:.4f}",
                adaptive_short_window=adaptive.short_window,
                adaptive_long_window=adaptive.long_window,
                adaptive_position_size_pct=f"{adaptive.position_size_pct:.4f}",
            )

        except APIError as exc:
            log_event(logger, logging.ERROR, "api_failure", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            log_event(logger, logging.ERROR, "loop_exception", error=str(exc))

        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
