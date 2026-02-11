from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd
import structlog

from indicators.custom import market_regime
from indicators.technical import adx
from indicators.volatility import atr
from strategies.base_strategy import BaseStrategy, Signal
from utils.time_utils import utc_now_ms

logger = structlog.get_logger("strategy_selector")


@dataclass
class StrategyHealth:
    rolling_pnls: deque[Decimal] = field(default_factory=lambda: deque(maxlen=30))
    weight: float = 1.0
    disabled_until_ms: int = 0
    last_reason: str = ""


class StrategySelector:
    def __init__(self, strategies: list[BaseStrategy]) -> None:
        self._strategies = {s.name: s for s in strategies}
        self._health: dict[str, StrategyHealth] = {s.name: StrategyHealth() for s in strategies}
        self._min_trades_for_deweight = 8
        self._min_trades_for_disable = 10
        self._deweight_win_rate = 0.40
        self._disable_win_rate = 0.30
        self._recovery_window_minutes = 180
        self._regime_map: dict[str, list[str]] = {
            "high_vol_trend": ["trend_following", "momentum"],
            "low_vol_trend": ["trend_following", "ema_crossover", "momentum"],
            "high_vol_range": ["mean_reversion", "funding_rate_arb"],
            "low_vol_range": ["mean_reversion", "grid_trading", "funding_rate_arb"],
        }

    @property
    def strategies(self) -> dict[str, BaseStrategy]:
        return dict(self._strategies)

    def detect_regime(self, df: pd.DataFrame) -> str:
        if len(df) < 200:
            return "low_vol_range"

        close = df["close"]
        adx_val, _, _ = adx(df["high"], df["low"], close)
        atr_val = atr(df["high"], df["low"], close)

        current_adx = adx_val.iloc[-1]
        current_atr = atr_val.iloc[-1]
        avg_atr = atr_val.rolling(50).mean().iloc[-1]

        from indicators.technical import ema as ema_fn
        ema200 = ema_fn(close, 200)
        ema_slope = (ema200.iloc[-1] - ema200.iloc[-10]) / ema200.iloc[-10] if ema200.iloc[-10] != 0 else 0

        vol_percentile = (atr_val.rank(pct=True)).iloc[-1]

        high_vol = current_atr > avg_atr or vol_percentile > 0.7
        strong_trend = current_adx > 25 and abs(ema_slope) > 0.002
        weak_trend = current_adx > 20 and not strong_trend

        if strong_trend and high_vol:
            return "high_vol_trend"
        if strong_trend or weak_trend:
            return "low_vol_trend"
        if high_vol:
            return "high_vol_range"
        return "low_vol_range"

    def select_strategies(self, df: pd.DataFrame) -> list[BaseStrategy]:
        regime = self.detect_regime(df)
        preferred = self._regime_map.get(regime, list(self._strategies.keys()))
        self._refresh_recovery_states()

        selected = []
        for name in preferred:
            strat = self._strategies.get(name)
            if strat and strat.enabled and not self._is_temporarily_disabled(name):
                selected.append(strat)

        if not selected:
            selected = [
                s for name, s in self._strategies.items()
                if s.enabled and not self._is_temporarily_disabled(name)
            ]

        return selected

    def generate_signals(self, symbol: str, df: pd.DataFrame) -> list[Signal]:
        active_strategies = self.select_strategies(df)
        signals: list[Signal] = []

        for strategy in active_strategies:
            if symbol not in strategy.symbols:
                continue
            signal = strategy.generate_signal(symbol, df)
            if signal:
                health = self._health.get(strategy.name, StrategyHealth())
                adjusted = max(0.0, min(1.0, signal.confidence * health.weight))
                signal.confidence = adjusted
                signal.metadata["strategy_weight"] = float(health.weight)
                signals.append(signal)

        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def get_best_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        signals = self.generate_signals(symbol, df)
        return signals[0] if signals else None

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.name] = strategy
        self._health[strategy.name] = StrategyHealth()

    def remove_strategy(self, name: str) -> None:
        self._strategies.pop(name, None)
        self._health.pop(name, None)

    def set_regime_map(self, regime: str, strategy_names: list[str]) -> None:
        self._regime_map[regime] = strategy_names

    def record_trade_result(self, strategy_name: str, realized_pnl: Decimal) -> None:
        health = self._health.get(strategy_name)
        strategy = self._strategies.get(strategy_name)
        if not health or not strategy:
            return
        health.rolling_pnls.append(realized_pnl)
        total = len(health.rolling_pnls)
        if total < self._min_trades_for_deweight:
            health.weight = 1.0
            health.last_reason = ""
            return
        wins = sum(1 for p in health.rolling_pnls if p > 0)
        win_rate = wins / total
        expectancy = sum(health.rolling_pnls, Decimal("0")) / Decimal(str(total))

        if total >= self._min_trades_for_disable and win_rate < self._disable_win_rate and expectancy < 0:
            health.weight = 0.0
            health.disabled_until_ms = utc_now_ms() + self._recovery_window_minutes * 60_000
            health.last_reason = (
                f"disabled: win_rate={win_rate:.2f}, expectancy={expectancy:.4f}"
            )
            strategy.disable()
            return

        if win_rate < self._deweight_win_rate or expectancy < 0:
            health.weight = max(0.3, win_rate)
            health.last_reason = (
                f"deweighted: win_rate={win_rate:.2f}, expectancy={expectancy:.4f}"
            )
            return

        if win_rate > 0.55 and expectancy > 0:
            health.weight = min(1.2, 0.8 + win_rate * 0.4)
            health.last_reason = f"boosted: win_rate={win_rate:.2f}"
            return

        health.weight = 1.0
        health.last_reason = ""

    def get_strategy_health(self, strategy_name: str) -> dict[str, str | float | int]:
        health = self._health.get(strategy_name)
        if not health:
            return {}
        return {
            "weight": health.weight,
            "disabled_until_ms": health.disabled_until_ms,
            "last_reason": health.last_reason,
            "rolling_trades": len(health.rolling_pnls),
        }

    def _is_temporarily_disabled(self, strategy_name: str) -> bool:
        health = self._health.get(strategy_name)
        if not health:
            return False
        return health.disabled_until_ms > utc_now_ms()

    def _refresh_recovery_states(self) -> None:
        now_ms = utc_now_ms()
        for name, health in self._health.items():
            if health.disabled_until_ms <= 0:
                continue
            if now_ms < health.disabled_until_ms:
                continue
            strategy = self._strategies.get(name)
            if strategy:
                strategy.enable()
            health.disabled_until_ms = 0
            health.weight = 1.0
            health.last_reason = "recovered"
            health.rolling_pnls.clear()
