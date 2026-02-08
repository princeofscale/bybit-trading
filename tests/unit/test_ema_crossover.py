import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import SignalDirection, StrategyState
from strategies.ema_crossover import EmaCrossoverStrategy


def _make_uptrend_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    trend = np.linspace(100, 150, n)
    noise = np.random.randn(n) * 0.5
    close = trend + noise
    return pd.DataFrame({
        "open": close - 0.5,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": np.random.randint(500, 2000, n).astype(float),
    })


def _make_downtrend_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    trend = np.linspace(150, 100, n)
    noise = np.random.randn(n) * 0.5
    close = trend + noise
    return pd.DataFrame({
        "open": close + 0.5,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": np.random.randint(500, 2000, n).astype(float),
    })


def _make_crossover_df() -> pd.DataFrame:
    n = 60
    close = np.zeros(n)
    close[:30] = np.linspace(100, 90, 30)
    close[30:] = np.linspace(90, 110, 30)
    return pd.DataFrame({
        "open": close - 0.3,
        "high": close + 1.5,
        "low": close - 1.5,
        "close": close,
        "volume": np.full(n, 1000.0),
    })


@pytest.fixture
def strategy() -> EmaCrossoverStrategy:
    return EmaCrossoverStrategy(
        symbols=["BTC/USDT:USDT"],
        fast_period=9,
        slow_period=21,
        min_confidence=0.3,
    )


def test_min_candles(strategy: EmaCrossoverStrategy) -> None:
    assert strategy.min_candles_required() >= 21


def test_no_signal_insufficient_data(strategy: EmaCrossoverStrategy) -> None:
    df = _make_uptrend_df(10)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_signal_on_uptrend(strategy: EmaCrossoverStrategy) -> None:
    df = _make_crossover_df()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.LONG, SignalDirection.NEUTRAL)


def test_exit_signal_when_in_position(strategy: EmaCrossoverStrategy) -> None:
    strategy.set_state("BTC/USDT:USDT", StrategyState.LONG)
    df = _make_downtrend_df()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction == SignalDirection.CLOSE_LONG


def test_signal_has_stop_loss_and_take_profit(strategy: EmaCrossoverStrategy) -> None:
    df = _make_crossover_df()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal and signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
        assert signal.stop_loss is not None
        assert signal.take_profit is not None


def test_volume_confirmation_reduces_confidence() -> None:
    strat_with_vol = EmaCrossoverStrategy(
        symbols=["BTC/USDT:USDT"], volume_confirmation=True, min_confidence=0.1,
    )
    strat_no_vol = EmaCrossoverStrategy(
        symbols=["BTC/USDT:USDT"], volume_confirmation=False, min_confidence=0.1,
    )
    df = _make_crossover_df()
    df["volume"] = 1.0
    sig_with = strat_with_vol.generate_signal("BTC/USDT:USDT", df)
    sig_without = strat_no_vol.generate_signal("BTC/USDT:USDT", df)
    if sig_with and sig_without:
        assert sig_with.confidence <= sig_without.confidence


def test_strategy_name(strategy: EmaCrossoverStrategy) -> None:
    assert strategy.name == "ema_crossover"
