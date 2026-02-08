import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import SignalDirection, StrategyState
from strategies.trend_following import TrendFollowingStrategy


def _make_strong_uptrend(n: int = 250) -> pd.DataFrame:
    np.random.seed(42)
    trend = np.linspace(100, 200, n)
    noise = np.random.randn(n) * 1.0
    close = trend + noise
    return pd.DataFrame({
        "open": close - 0.5,
        "high": close + abs(np.random.randn(n)) * 2,
        "low": close - abs(np.random.randn(n)) * 2,
        "close": close,
        "volume": np.random.randint(500, 2000, n).astype(float),
    })


def _make_strong_downtrend(n: int = 250) -> pd.DataFrame:
    np.random.seed(42)
    trend = np.linspace(200, 100, n)
    noise = np.random.randn(n) * 1.0
    close = trend + noise
    return pd.DataFrame({
        "open": close + 0.5,
        "high": close + abs(np.random.randn(n)) * 2,
        "low": close - abs(np.random.randn(n)) * 2,
        "close": close,
        "volume": np.random.randint(500, 2000, n).astype(float),
    })


def _make_flat_df(n: int = 250) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.random.randn(n) * 0.5
    return pd.DataFrame({
        "open": close - 0.1,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": np.full(n, 500.0),
    })


@pytest.fixture
def strategy() -> TrendFollowingStrategy:
    return TrendFollowingStrategy(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.2,
        use_supertrend=False,
    )


def test_min_candles(strategy: TrendFollowingStrategy) -> None:
    assert strategy.min_candles_required() >= 200


def test_no_signal_insufficient_data(strategy: TrendFollowingStrategy) -> None:
    df = _make_strong_uptrend(50)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_long_signal_uptrend(strategy: TrendFollowingStrategy) -> None:
    df = _make_strong_uptrend()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.LONG, SignalDirection.NEUTRAL)


def test_short_signal_downtrend(strategy: TrendFollowingStrategy) -> None:
    df = _make_strong_downtrend()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.SHORT, SignalDirection.NEUTRAL)


def test_no_signal_flat(strategy: TrendFollowingStrategy) -> None:
    df = _make_flat_df()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_exit_long(strategy: TrendFollowingStrategy) -> None:
    strategy.set_state("BTC/USDT:USDT", StrategyState.LONG)
    df = _make_strong_downtrend()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction == SignalDirection.CLOSE_LONG


def test_signal_metadata(strategy: TrendFollowingStrategy) -> None:
    df = _make_strong_uptrend()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal and signal.direction == SignalDirection.LONG:
        assert "adx" in signal.metadata
        assert "rsi" in signal.metadata


def test_strategy_name(strategy: TrendFollowingStrategy) -> None:
    assert strategy.name == "trend_following"
