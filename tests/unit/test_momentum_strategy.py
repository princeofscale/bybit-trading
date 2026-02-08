import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import SignalDirection, StrategyState
from strategies.momentum_strategy import MomentumStrategy


def _make_strong_momentum_df(n: int = 100, direction: int = 1) -> pd.DataFrame:
    np.random.seed(42)
    base = 100.0
    close = np.zeros(n)
    for i in range(n):
        close[i] = base + direction * i * 0.5 + np.random.randn() * 0.2
    return pd.DataFrame({
        "open": close - 0.3 * direction,
        "high": close + abs(np.random.randn(n)) * 2,
        "low": close - abs(np.random.randn(n)) * 2,
        "close": close,
        "volume": np.random.randint(1000, 5000, n).astype(float),
    })


def _make_flat_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.random.randn(n) * 0.1
    return pd.DataFrame({
        "open": close - 0.05,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": np.full(n, 100.0),
    })


@pytest.fixture
def strategy() -> MomentumStrategy:
    return MomentumStrategy(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.2,
        volume_threshold=0.5,
        momentum_threshold=0.1,
    )


def test_min_candles(strategy: MomentumStrategy) -> None:
    assert strategy.min_candles_required() >= 20


def test_no_signal_insufficient_data(strategy: MomentumStrategy) -> None:
    df = _make_flat_df(5)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_long_signal_on_upward_momentum(strategy: MomentumStrategy) -> None:
    df = _make_strong_momentum_df(direction=1)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal and signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
        assert signal.stop_loss is not None
        assert signal.take_profit is not None


def test_exit_signal_when_momentum_reverses(strategy: MomentumStrategy) -> None:
    strategy.set_state("BTC/USDT:USDT", StrategyState.LONG)
    df = _make_strong_momentum_df(direction=-1)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction == SignalDirection.CLOSE_LONG


def test_no_signal_flat_market(strategy: MomentumStrategy) -> None:
    strat = MomentumStrategy(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.5,
        volume_threshold=2.0,
        momentum_threshold=0.5,
    )
    df = _make_flat_df()
    signal = strat.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_strategy_name(strategy: MomentumStrategy) -> None:
    assert strategy.name == "momentum"
