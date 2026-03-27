"""Trading strategy implementations."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from utils import safe_float


@dataclass
class StrategySignal:
    action: str  # BUY / SELL / HOLD
    reason: str
    short_ma: float
    long_ma: float
    momentum: float


class MovingAverageMomentumStrategy:
    def __init__(self, short_window: int, long_window: int) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.prices: deque[float] = deque(maxlen=long_window + 2)

    def update_price(self, price: float) -> None:
        self.prices.append(safe_float(price))

    def _ma(self, window: int, offset_from_end: int = 0) -> float:
        if len(self.prices) < window + offset_from_end:
            return 0.0
        end = len(self.prices) - offset_from_end
        start = end - window
        segment = list(self.prices)[start:end]
        return sum(segment) / float(window)

    def _momentum(self) -> float:
        if len(self.prices) < self.short_window + 1:
            return 0.0
        latest = self.prices[-1]
        past = self.prices[-1 - self.short_window]
        return latest - past

    def generate_signal(self, position: object | None = None) -> StrategySignal:
        if len(self.prices) < self.long_window + 1:
            return StrategySignal(
                action="HOLD",
                reason="insufficient_history",
                short_ma=0.0,
                long_ma=0.0,
                momentum=0.0,
            )

        prev_short = self._ma(self.short_window, offset_from_end=1)
        prev_long = self._ma(self.long_window, offset_from_end=1)
        curr_short = self._ma(self.short_window, offset_from_end=0)
        curr_long = self._ma(self.long_window, offset_from_end=0)
        momentum = self._momentum()

        bullish_cross = prev_short <= prev_long and curr_short > curr_long
        bearish_cross = prev_short >= prev_long and curr_short < curr_long

        if bullish_cross and momentum > 0:
            return StrategySignal("BUY", "bullish_cross_with_positive_momentum", curr_short, curr_long, momentum)
        if bearish_cross:
            return StrategySignal("SELL", "bearish_cross", curr_short, curr_long, momentum)
        return StrategySignal("HOLD", "no_actionable_signal", curr_short, curr_long, momentum)

    def reconfigure(self, short_window: int, long_window: int) -> None:
        """Update windows in-place while retaining recent prices."""
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.prices = deque(self.prices, maxlen=long_window + 2)


class DipLadderStrategy:
    """Mimics staged dip buying observed in the recording.

    Entry pattern:
    - Wait for a local pullback from recent high.
    - Require a small rebound from the local low before first entry.
    - Add more tranches only on further dips from last buy.
    - Exit is handled by risk model (stop-loss + trailing take-profit), not by this class.
    """

    def __init__(self, dip_step_pct: float, rebound_pct: float, lookback: int, max_tranches: int) -> None:
        if dip_step_pct <= 0:
            raise ValueError("dip_step_pct must be > 0")
        if rebound_pct < 0:
            raise ValueError("rebound_pct must be >= 0")
        if lookback < 5:
            raise ValueError("lookback must be >= 5")
        if max_tranches < 1:
            raise ValueError("max_tranches must be >= 1")
        self.dip_step_pct = dip_step_pct
        self.rebound_pct = rebound_pct
        self.lookback = lookback
        self.max_tranches = max_tranches
        self.prices: deque[float] = deque(maxlen=lookback)

    def update_price(self, price: float) -> None:
        self.prices.append(safe_float(price))

    def generate_signal(self, position: object | None = None) -> StrategySignal:
        if len(self.prices) < self.lookback:
            return StrategySignal("HOLD", "insufficient_history", 0.0, 0.0, 0.0)

        current = self.prices[-1]
        recent_low = min(self.prices)
        recent_high = max(self.prices)
        drawdown = (recent_high - current) / recent_high if recent_high > 0 else 0.0
        rebound = (current - recent_low) / recent_low if recent_low > 0 else 0.0

        qty = safe_float(getattr(position, "quantity", 0.0), 0.0)
        last_buy_price = safe_float(getattr(position, "last_buy_price", 0.0), 0.0)
        tranche_count = int(getattr(position, "tranche_count", 0) or 0)

        # First buy: price is still depressed, but has started to bounce.
        if qty <= 0:
            if drawdown >= self.dip_step_pct and rebound >= self.rebound_pct:
                return StrategySignal("BUY", "first_tranche_after_dip_rebound", drawdown, rebound, 0.0)
            return StrategySignal("HOLD", "wait_for_dip_rebound", drawdown, rebound, 0.0)

        # Additional buys: ladder in lower.
        if tranche_count < self.max_tranches and last_buy_price > 0:
            if current <= last_buy_price * (1 - self.dip_step_pct):
                return StrategySignal("BUY", "ladder_add_on_next_dip", drawdown, rebound, 0.0)

        return StrategySignal("HOLD", "hold_until_exit_model", drawdown, rebound, 0.0)
