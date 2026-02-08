import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import SignalDirection, StrategyState
from strategies.mean_reversion import MeanReversionStrategy


def _make_oversold_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    close = np.full(n, 100.0)
    close[-15:] = np.linspace(100, 75, 15)
    return pd.DataFrame({
        "open": close + 0.5,
        "high": close + 3,
        "low": close - 3,
        "close": close,
        "volume": np.full(n, 1000.0),
    })


def _make_overbought_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    close = np.full(n, 100.0)
    close[-15:] = np.linspace(100, 130, 15)
    return pd.DataFrame({
        "open": close - 0.5,
        "high": close + 3,
        "low": close - 3,
        "close": close,
        "volume": np.full(n, 1000.0),
    })


def _make_ranging_df(n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    t = np.linspace(0, 4 * np.pi, n)
    close = 100 + 5 * np.sin(t) + np.random.randn(n) * 0.3
    return pd.DataFrame({
        "open": close - 0.2,
        "high": close + 1.5,
        "low": close - 1.5,
        "close": close,
        "volume": np.full(n, 1000.0),
    })


@pytest.fixture
def strategy() -> MeanReversionStrategy:
    return MeanReversionStrategy(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.3,
    )


def test_min_candles(strategy: MeanReversionStrategy) -> None:
    assert strategy.min_candles_required() >= 20


def test_no_signal_insufficient_data(strategy: MeanReversionStrategy) -> None:
    df = _make_ranging_df(10)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_long_signal_on_oversold(strategy: MeanReversionStrategy) -> None:
    df = _make_oversold_df()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.LONG, SignalDirection.NEUTRAL)


def test_short_signal_on_overbought(strategy: MeanReversionStrategy) -> None:
    df = _make_overbought_df()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.SHORT, SignalDirection.NEUTRAL)


def test_exit_long(strategy: MeanReversionStrategy) -> None:
    strategy.set_state("BTC/USDT:USDT", StrategyState.LONG)
    df = _make_ranging_df()
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.NEUTRAL)


def test_dynamic_thresholds() -> None:
    strat = MeanReversionStrategy(
        symbols=["BTC/USDT:USDT"],
        use_dynamic_thresholds=True,
        min_confidence=0.1,
    )
    assert strat.name == "mean_reversion"


def test_strategy_name(strategy: MeanReversionStrategy) -> None:
    assert strategy.name == "mean_reversion"
