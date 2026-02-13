from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd
import structlog

from indicators.custom import market_regime
from indicators.technical import adx
from indicators.volatility import atr
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection
from utils.time_utils import utc_now_ms

if TYPE_CHECKING:
    from ml.prediction import PredictionService

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
        self._ml_service: PredictionService | None = None
        self._ml_boost: float = 0.2
        self._ml_penalize: float = 0.3
        self._ml_threshold: float = 0.6

    @property
    def strategies(self) -> dict[str, BaseStrategy]:
        return dict(self._strategies)

    def set_ml_service(
        self,
        service: PredictionService | None,
        boost: float = 0.2,
        penalize: float = 0.3,
        threshold: float = 0.6,
    ) -> None:
        self._ml_service = service
        self._ml_boost = boost
        self._ml_penalize = penalize
        self._ml_threshold = threshold

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

        ml_prediction = None
        if self._ml_service is not None:
            try:
                ml_prediction = self._ml_service.predict(df)
            except Exception:
                ml_prediction = None

        for strategy in active_strategies:
            if symbol not in strategy.symbols:
                continue
            signal = strategy.generate_signal(symbol, df)
            if signal:
                health = self._health.get(strategy.name, StrategyHealth())
                adjusted = max(0.0, min(1.0, signal.confidence * health.weight))
                signal.confidence = adjusted
                signal.metadata["strategy_weight"] = float(health.weight)
                signal = self._apply_ml_adjustment(signal, ml_prediction)
                signals.append(signal)

        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def _apply_ml_adjustment(self, signal: Signal, ml_prediction: object | None) -> Signal:
        if ml_prediction is None:
            return signal
        ml_dir = ml_prediction.direction
        ml_conf = ml_prediction.confidence
        ml_prob = ml_prediction.probability

        signal.metadata["ml_direction"] = {"long": 1.0, "short": -1.0, "neutral": 0.0}.get(ml_dir, 0.0)
        signal.metadata["ml_confidence"] = ml_conf
        signal.metadata["ml_probability"] = ml_prob

        if ml_conf < self._ml_threshold:
            return signal

        signal_is_long = signal.direction in (SignalDirection.LONG,)
        signal_is_short = signal.direction in (SignalDirection.SHORT,)
        ml_agrees = (signal_is_long and ml_dir == "long") or (signal_is_short and ml_dir == "short")
        ml_disagrees = (signal_is_long and ml_dir == "short") or (signal_is_short and ml_dir == "long")

        if ml_agrees:
            signal.confidence = min(1.0, signal.confidence + self._ml_boost)
        elif ml_disagrees:
            signal.confidence = max(0.0, signal.confidence - self._ml_penalize)

        return signal

    def get_best_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        signals = self.generate_signals(symbol, df)
        return signals[0] if signals else None

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.name] = strategy
        self._health[strategy.name] = StrategyHealth()

    def remove_strategy(self, name: str) -> None:
        self._strategies.pop(name, None)
        self._health.pop(name, None)

    def update_strategy_weights(self, allocations: dict[str, Decimal]) -> None:
        if not allocations:
            return
        max_alloc = max(float(v) for v in allocations.values()) if allocations else 1.0
        for name, alloc in allocations.items():
            health = self._health.get(name)
            if health:
                normalized = float(alloc) / max_alloc if max_alloc > 0 else 1.0
                health.weight = max(0.3, min(1.5, normalized * 1.2))

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
