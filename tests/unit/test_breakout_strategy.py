import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import SignalDirection, StrategyState
from strategies.breakout_strategy import BreakoutStrategy


def _make_squeeze_then_breakout(n: int = 80, direction: int = 1) -> pd.DataFrame:
    np.random.seed(42)
    close = np.full(n, 100.0)
    close[:60] = 100 + np.random.randn(60) * 0.5
    if direction == 1:
        close[60:] = np.linspace(100, 115, 20)
    else:
        close[60:] = np.linspace(100, 85, 20)

    volume = np.full(n, 500.0)
    volume[-5:] = 3000.0

    return pd.DataFrame({
        "open": close - 0.2 * direction,
        "high": close + abs(np.random.randn(n)),
        "low": close - abs(np.random.randn(n)),
        "close": close,
        "volume": volume,
    })


def _make_ranging_df(n: int = 80) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.random.randn(n) * 2
    return pd.DataFrame({
        "open": close - 0.1,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": np.full(n, 500.0),
    })


@pytest.fixture
def strategy() -> BreakoutStrategy:
    return BreakoutStrategy(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.2,
        volume_threshold=1.0,
    )


def test_min_candles(strategy: BreakoutStrategy) -> None:
    assert strategy.min_candles_required() >= 20


def test_no_signal_ranging(strategy: BreakoutStrategy) -> None:
    strat = BreakoutStrategy(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.5,
        volume_threshold=3.0,
    )
    df = _make_ranging_df()
    signal = strat.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_signal_on_upside_breakout(strategy: BreakoutStrategy) -> None:
    df = _make_squeeze_then_breakout(direction=1)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.LONG, SignalDirection.SHORT)
        assert signal.stop_loss is not None


def test_exit_long_below_middle(strategy: BreakoutStrategy) -> None:
    strategy.set_state("BTC/USDT:USDT", StrategyState.LONG)
    df = _make_squeeze_then_breakout(direction=-1)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction == SignalDirection.CLOSE_LONG


def test_no_signal_without_volume() -> None:
    strat = BreakoutStrategy(
        symbols=["BTC/USDT:USDT"],
        volume_threshold=5.0,
        min_confidence=0.1,
    )
    df = _make_squeeze_then_breakout(direction=1)
    df["volume"] = 100.0
    signal = strat.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_strategy_name(strategy: BreakoutStrategy) -> None:
    assert strategy.name == "breakout"
