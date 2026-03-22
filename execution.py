"""Signal execution layer with DRY_RUN and duplicate protections."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from api_client import RoostooClient
from logger import log_event
from risk import PairConstraints, PositionState, RiskDecision, RiskManager
from utils import extract_order_id


@dataclass
class ExecutionResult:
    attempted: bool
    executed: bool
    action: str
    reason: str
    quantity: float = 0.0
    order_id: str = ""
    response: dict[str, Any] | None = None


class ExecutionEngine:
    def __init__(
        self,
        client: RoostooClient,
        risk: RiskManager,
        logger: logging.Logger,
        pair: str,
        position_size_pct: float,
        dry_run: bool,
        constraints: PairConstraints,
    ) -> None:
        self.client = client
        self.risk = risk
        self.logger = logger
        self.pair = pair
        self.position_size_pct = position_size_pct
        self.dry_run = dry_run
        self.constraints = constraints
        self._last_order_fingerprint = ""

    def _fingerprint(self, action: str, quantity: float) -> str:
        return f"{action}:{self.pair}:{quantity:.12f}"

    def maybe_execute(
        self,
        action: str,
        signal_reason: str,
        last_price: float,
        quote_balance: float,
        base_balance: float,
        position: PositionState,
        max_position_usd: float,
    ) -> ExecutionResult:
        action = action.upper()
        if action not in {"BUY", "SELL"}:
            return ExecutionResult(False, False, "HOLD", f"skip_{signal_reason}")

        if action == "BUY":
            budget = max_position_usd * self.position_size_pct
            quantity = budget / last_price if last_price > 0 else 0.0
        else:
            quantity = min(base_balance, position.quantity if position.quantity > 0 else base_balance)

        risk_decision: RiskDecision = self.risk.enforce(
            side=action,
            quantity=quantity,
            last_price=last_price,
            quote_balance=quote_balance,
            base_balance=base_balance,
            constraints=self.constraints,
            position=position,
        )

        if not risk_decision.allowed:
            return ExecutionResult(True, False, action, risk_decision.reason)

        qty = risk_decision.quantity
        fp = self._fingerprint(action, qty)
        if fp == self._last_order_fingerprint:
            return ExecutionResult(True, False, action, "duplicate_order_prevented", quantity=qty)

        pending = self.client.get_pending_count()
        pending_count = int(pending.get("count", pending.get("pending_count", 0)))
        if pending_count > 0:
            return ExecutionResult(True, False, action, "pending_order_exists", quantity=qty, response=pending)

        if self.dry_run:
            log_event(
                self.logger,
                logging.INFO,
                "dry_run_order",
                action=action,
                reason=signal_reason,
                quantity=qty,
                price=last_price,
            )
            self._last_order_fingerprint = fp
            return ExecutionResult(True, True, action, "dry_run", quantity=qty)

        response = self.client.place_order(self.pair, action, "MARKET", qty)
        order_id = extract_order_id(response)
        self._last_order_fingerprint = fp

        if order_id:
            position.last_trade_ts = datetime.now(tz=timezone.utc).timestamp()
            if action == "BUY":
                position.quantity += qty
                position.avg_entry_price = last_price
            elif action == "SELL":
                position.quantity = max(0.0, position.quantity - qty)
                if position.quantity == 0:
                    position.avg_entry_price = 0.0

        return ExecutionResult(True, True, action, "order_submitted", quantity=qty, order_id=order_id, response=response)
