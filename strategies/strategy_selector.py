import pandas as pd
import structlog

from indicators.custom import market_regime
from indicators.technical import adx
from indicators.volatility import atr
from strategies.base_strategy import BaseStrategy, Signal

logger = structlog.get_logger("strategy_selector")


class StrategySelector:
    def __init__(self, strategies: list[BaseStrategy]) -> None:
        self._strategies = {s.name: s for s in strategies}
        self._regime_map: dict[str, list[str]] = {
            "high_vol_trend": ["trend_following", "momentum", "breakout"],
            "low_vol_trend": ["trend_following", "ema_crossover"],
            "high_vol_range": ["mean_reversion", "grid_trading"],
            "low_vol_range": ["grid_trading", "mean_reversion", "funding_rate_arb"],
        }

    @property
    def strategies(self) -> dict[str, BaseStrategy]:
        return dict(self._strategies)

    def detect_regime(self, df: pd.DataFrame) -> str:
        if len(df) < 60:
            return "low_vol_range"

        adx_val, _, _ = adx(df["high"], df["low"], df["close"])
        atr_val = atr(df["high"], df["low"], df["close"])

        regimes = market_regime(df["close"], adx_val, atr_val)
        return regimes.iloc[-1]

    def select_strategies(self, df: pd.DataFrame) -> list[BaseStrategy]:
        regime = self.detect_regime(df)
        preferred = self._regime_map.get(regime, list(self._strategies.keys()))

        selected = []
        for name in preferred:
            strat = self._strategies.get(name)
            if strat and strat.enabled:
                selected.append(strat)

        if not selected:
            selected = [s for s in self._strategies.values() if s.enabled]

        return selected

    def generate_signals(self, symbol: str, df: pd.DataFrame) -> list[Signal]:
        active_strategies = self.select_strategies(df)
        signals: list[Signal] = []

        for strategy in active_strategies:
            if symbol not in strategy.symbols:
                continue
            signal = strategy.generate_signal(symbol, df)
            if signal:
                signals.append(signal)

        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def get_best_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        signals = self.generate_signals(symbol, df)
        return signals[0] if signals else None

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.name] = strategy

    def remove_strategy(self, name: str) -> None:
        self._strategies.pop(name, None)

    def set_regime_map(self, regime: str, strategy_names: list[str]) -> None:
        self._regime_map[regime] = strategy_names
