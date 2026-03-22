"""Simple moving-average crossover + momentum strategy."""

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

    def generate_signal(self) -> StrategySignal:
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
