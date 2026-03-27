"""Adaptive performance tracking and strategy tuning."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque


@dataclass(frozen=True)
class AdaptiveConfig:
    enabled: bool
    reevaluate_loops: int
    min_short_window: int
    max_short_window: int
    min_long_window: int
    max_long_window: int
    min_position_size_pct: float
    max_position_size_pct: float
    drawdown_threshold: float
    loss_streak_threshold: int
    history_window: int


@dataclass(frozen=True)
class AdaptiveDecision:
    changed: bool
    reason: str
    new_short_window: int
    new_long_window: int
    new_position_size_pct: float
    rolling_return: float
    total_return: float
    drawdown: float
    win_rate: float


class AdaptiveController:
    def __init__(self, config: AdaptiveConfig, initial_short: int, initial_long: int, initial_pos_pct: float) -> None:
        self.config = config
        self.short_window = initial_short
        self.long_window = initial_long
        self.position_size_pct = initial_pos_pct

        self.loop_count = 0
        self.last_reconfigure_loop = 0
        self.initial_portfolio_value = 0.0
        self.latest_portfolio_value = 0.0
        self.peak_portfolio_value = 0.0

        self.portfolio_history: Deque[float] = deque(maxlen=max(5, config.history_window))
        self.trade_wins: Deque[int] = deque(maxlen=50)
        self.recent_loss_streak = 0
        self.realized_pnl = 0.0

    def on_portfolio_value(self, portfolio_value: float) -> None:
        self.loop_count += 1
        if self.initial_portfolio_value <= 0:
            self.initial_portfolio_value = portfolio_value
            self.peak_portfolio_value = portfolio_value
        self.latest_portfolio_value = portfolio_value
        self.peak_portfolio_value = max(self.peak_portfolio_value, portfolio_value)
        self.portfolio_history.append(portfolio_value)

    def on_realized_trade_pnl(self, pnl: float) -> None:
        self.realized_pnl += pnl
        is_win = int(pnl > 0)
        self.trade_wins.append(is_win)
        if is_win:
            self.recent_loss_streak = 0
        else:
            self.recent_loss_streak += 1

    def metrics(self) -> tuple[float, float, float, float]:
        if self.initial_portfolio_value <= 0:
            return 0.0, 0.0, 0.0, 0.0

        total_return = (self.latest_portfolio_value - self.initial_portfolio_value) / self.initial_portfolio_value
        if len(self.portfolio_history) >= 2 and self.portfolio_history[0] > 0:
            rolling_return = (self.portfolio_history[-1] - self.portfolio_history[0]) / self.portfolio_history[0]
        else:
            rolling_return = 0.0

        drawdown = 0.0
        if self.peak_portfolio_value > 0:
            drawdown = (self.peak_portfolio_value - self.latest_portfolio_value) / self.peak_portfolio_value

        if self.trade_wins:
            win_rate = sum(self.trade_wins) / float(len(self.trade_wins))
        else:
            win_rate = 0.5
        return total_return, rolling_return, drawdown, win_rate

    def maybe_reconfigure(self) -> AdaptiveDecision:
        total_return, rolling_return, drawdown, win_rate = self.metrics()

        if not self.config.enabled:
            return AdaptiveDecision(
                False,
                "adaptive_disabled",
                self.short_window,
                self.long_window,
                self.position_size_pct,
                rolling_return,
                total_return,
                drawdown,
                win_rate,
            )

        if self.loop_count - self.last_reconfigure_loop < self.config.reevaluate_loops:
            return AdaptiveDecision(
                False,
                "reevaluate_interval_not_reached",
                self.short_window,
                self.long_window,
                self.position_size_pct,
                rolling_return,
                total_return,
                drawdown,
                win_rate,
            )

        loss_triggered = self.recent_loss_streak >= self.config.loss_streak_threshold
        drawdown_triggered = drawdown >= self.config.drawdown_threshold

        if loss_triggered or drawdown_triggered:
            # De-risk and smooth signals after poor performance.
            next_short = min(self.config.max_short_window, self.short_window + 1)
            next_long = min(self.config.max_long_window, self.long_window + 3)
            next_long = max(next_long, next_short + 2)
            next_pos = max(self.config.min_position_size_pct, self.position_size_pct * 0.85)
            reason = "derisk_after_losses_or_drawdown"
        elif rolling_return > 0.015 and drawdown < (self.config.drawdown_threshold / 2):
            # Carefully increase aggressiveness when performance is strong.
            next_short = max(self.config.min_short_window, self.short_window - 1)
            next_long = max(self.config.min_long_window, self.long_window - 2)
            next_long = max(next_long, next_short + 2)
            next_pos = min(self.config.max_position_size_pct, self.position_size_pct * 1.08)
            reason = "increase_aggression_on_strength"
        else:
            self.last_reconfigure_loop = self.loop_count
            return AdaptiveDecision(
                False,
                "no_change",
                self.short_window,
                self.long_window,
                self.position_size_pct,
                rolling_return,
                total_return,
                drawdown,
                win_rate,
            )

        changed = (
            next_short != self.short_window
            or next_long != self.long_window
            or abs(next_pos - self.position_size_pct) > 1e-12
        )
        self.short_window = next_short
        self.long_window = next_long
        self.position_size_pct = next_pos
        self.last_reconfigure_loop = self.loop_count
        if changed and (loss_triggered or drawdown_triggered):
            self.recent_loss_streak = 0

        return AdaptiveDecision(
            changed,
            reason,
            self.short_window,
            self.long_window,
            self.position_size_pct,
            rolling_return,
            total_return,
            drawdown,
            win_rate,
        )
