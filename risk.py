"""Risk controls and pair constraints for order safety."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from utils import floor_to_precision, safe_float


@dataclass
class PairConstraints:
    pair: str
    min_order: float
    amount_precision: int
    tradable: bool
    found: bool = False


@dataclass
class PositionState:
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    last_trade_ts: float = 0.0

    @property
    def has_position(self) -> bool:
        return self.quantity > 0


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    quantity: float


class RiskManager:
    def __init__(
        self,
        max_position_usd: float,
        min_cash_reserve_usd: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        cooldown_seconds: int,
    ) -> None:
        self.max_position_usd = max_position_usd
        self.min_cash_reserve_usd = min_cash_reserve_usd
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.cooldown_seconds = cooldown_seconds

    @staticmethod
    def parse_pair_constraints(exchange_info: dict[str, Any], target_pair: str) -> PairConstraints:
        pair_upper = target_pair.upper()
        candidates: list[dict[str, Any]] = []

        symbols = exchange_info.get("symbols")
        if isinstance(symbols, list):
            candidates.extend([x for x in symbols if isinstance(x, dict)])

        data = exchange_info.get("data")
        if isinstance(data, list):
            candidates.extend([x for x in data if isinstance(x, dict)])

        for item in candidates:
            symbol_value = str(item.get("pair", item.get("symbol", ""))).upper()
            if symbol_value != pair_upper:
                continue

            min_order = safe_float(item.get("MiniOrder", item.get("minOrder", item.get("minQty", 0.0))), 0.0)
            amount_precision = int(item.get("AmountPrecision", item.get("amountPrecision", 6)))
            status = str(item.get("status", "TRADING")).upper()
            tradable_raw = item.get("tradable")
            tradable = bool(tradable_raw) if tradable_raw is not None else status in {"TRADING", "ENABLED"}
            return PairConstraints(
                pair=pair_upper,
                min_order=min_order,
                amount_precision=amount_precision,
                tradable=tradable,
                found=True,
            )

        # If pair is not discovered from exchangeInfo, fail closed.
        return PairConstraints(pair=pair_upper, min_order=0.0, amount_precision=6, tradable=False, found=False)

    @staticmethod
    def in_cooldown(position: PositionState, cooldown_seconds: int) -> bool:
        if position.last_trade_ts <= 0:
            return False
        now = datetime.now(tz=timezone.utc).timestamp()
        return (now - position.last_trade_ts) < cooldown_seconds

    def check_stop_or_take_profit(self, position: PositionState, current_price: float) -> tuple[bool, str]:
        if not position.has_position or position.avg_entry_price <= 0:
            return False, "no_open_position"

        if current_price <= position.avg_entry_price * (1 - self.stop_loss_pct):
            return True, "stop_loss_hit"

        if current_price >= position.avg_entry_price * (1 + self.take_profit_pct):
            return True, "take_profit_hit"

        return False, "risk_not_triggered"

    def enforce(
        self,
        side: str,
        quantity: float,
        last_price: float,
        quote_balance: float,
        base_balance: float,
        constraints: PairConstraints,
        position: PositionState,
    ) -> RiskDecision:
        if not constraints.tradable:
            return RiskDecision(False, "pair_not_tradable", 0.0)

        if self.in_cooldown(position, self.cooldown_seconds):
            return RiskDecision(False, "cooldown_active", 0.0)

        qty = max(0.0, floor_to_precision(quantity, constraints.amount_precision))
        if qty <= 0:
            return RiskDecision(False, "quantity_too_small_after_rounding", 0.0)

        notional = qty * last_price
        if constraints.min_order > 0 and qty < constraints.min_order:
            return RiskDecision(False, "below_min_order", 0.0)

        if side.upper() == "BUY":
            if notional > self.max_position_usd:
                return RiskDecision(False, "max_position_exceeded", 0.0)
            if quote_balance - notional < self.min_cash_reserve_usd:
                return RiskDecision(False, "cash_reserve_violation", 0.0)
            return RiskDecision(True, "buy_allowed", qty)

        if side.upper() == "SELL":
            if qty > base_balance:
                return RiskDecision(False, "insufficient_base_balance", 0.0)
            return RiskDecision(True, "sell_allowed", qty)

        return RiskDecision(False, "invalid_side", 0.0)
