import numpy as np
import pandas as pd
import pytest
from decimal import Decimal

from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.strategy_selector import StrategySelector


class AlwaysLongStrategy(BaseStrategy):
    def __init__(self, symbols: list[str], confidence: float = 0.8) -> None:
        super().__init__("always_long", symbols)
        self._confidence = confidence

    def min_candles_required(self) -> int:
        return 5

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        return Signal(
            symbol=symbol, direction=SignalDirection.LONG,
            confidence=self._confidence, strategy_name=self._name,
        )


class AlwaysShortStrategy(BaseStrategy):
    def __init__(self, symbols: list[str], confidence: float = 0.6) -> None:
        super().__init__("always_short", symbols)
        self._confidence = confidence

    def min_candles_required(self) -> int:
        return 5

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        return Signal(
            symbol=symbol, direction=SignalDirection.SHORT,
            confidence=self._confidence, strategy_name=self._name,
        )


class NeverSignalStrategy(BaseStrategy):
    def __init__(self, symbols: list[str]) -> None:
        super().__init__("never_signal", symbols)

    def min_candles_required(self) -> int:
        return 5

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        return None


def _make_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    close = np.cumsum(np.random.randn(n)) + 100
    return pd.DataFrame({
        "open": close - 0.5,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": np.random.randint(100, 1000, n).astype(float),
    })


@pytest.fixture
def selector() -> StrategySelector:
    symbols = ["BTC/USDT:USDT"]
    return StrategySelector([
        AlwaysLongStrategy(symbols, confidence=0.8),
        AlwaysShortStrategy(symbols, confidence=0.6),
        NeverSignalStrategy(symbols),
    ])


def test_generate_signals_returns_sorted(selector: StrategySelector) -> None:
    df = _make_df()
    signals = selector.generate_signals("BTC/USDT:USDT", df)
    assert len(signals) >= 1
    for i in range(len(signals) - 1):
        assert signals[i].confidence >= signals[i + 1].confidence


def test_get_best_signal(selector: StrategySelector) -> None:
    df = _make_df()
    best = selector.get_best_signal("BTC/USDT:USDT", df)
    assert best is not None
    assert best.confidence == 0.8
    assert best.direction == SignalDirection.LONG


def test_no_signal_when_all_disabled(selector: StrategySelector) -> None:
    for strat in selector.strategies.values():
        strat.disable()
    df = _make_df()
    signals = selector.generate_signals("BTC/USDT:USDT", df)
    assert len(signals) == 0


def test_add_strategy(selector: StrategySelector) -> None:
    new_strat = NeverSignalStrategy(["BTC/USDT:USDT"])
    selector.add_strategy(new_strat)
    assert "never_signal" in selector.strategies


def test_remove_strategy(selector: StrategySelector) -> None:
    selector.remove_strategy("always_long")
    assert "always_long" not in selector.strategies


def test_detect_regime(selector: StrategySelector) -> None:
    df = _make_df()
    regime = selector.detect_regime(df)
    valid_regimes = {"high_vol_trend", "low_vol_trend", "high_vol_range", "low_vol_range"}
    assert regime in valid_regimes


def test_select_strategies_returns_enabled(selector: StrategySelector) -> None:
    df = _make_df()
    selected = selector.select_strategies(df)
    assert all(s.enabled for s in selected)


def test_set_regime_map(selector: StrategySelector) -> None:
    selector.set_regime_map("custom_regime", ["always_long"])
    df = _make_df()
    best = selector.get_best_signal("BTC/USDT:USDT", df)
    assert best is not None


def test_wrong_symbol_no_signal(selector: StrategySelector) -> None:
    df = _make_df()
    signals = selector.generate_signals("SOL/USDT:USDT", df)
    assert len(signals) == 0


def test_strategy_deweights_after_poor_results(selector: StrategySelector) -> None:
    for _ in range(8):
        selector.record_trade_result("always_long", Decimal("-10"))
    df = _make_df()
    sigs = selector.generate_signals("BTC/USDT:USDT", df)
    best = sigs[0]
    assert best.strategy_name == "always_short"


def test_strategy_disables_after_severe_degradation(selector: StrategySelector) -> None:
    for _ in range(10):
        selector.record_trade_result("always_long", Decimal("-10"))
    health = selector.get_strategy_health("always_long")
    assert health.get("weight") == 0.0
    df = _make_df()
    sigs = selector.generate_signals("BTC/USDT:USDT", df)
    assert all(s.strategy_name != "always_long" for s in sigs)
