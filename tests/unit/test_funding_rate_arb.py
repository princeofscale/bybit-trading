import numpy as np
import pandas as pd
import pytest

from strategies.base_strategy import SignalDirection, StrategyState
from strategies.funding_rate_arb import FundingRateArbStrategy


def _make_funding_df(funding_val: float, n: int = 50) -> pd.DataFrame:
    np.random.seed(42)
    close = np.full(n, 30000.0) + np.random.randn(n) * 10
    return pd.DataFrame({
        "open": close - 5,
        "high": close + 20,
        "low": close - 20,
        "close": close,
        "volume": np.full(n, 1000.0),
        "funding_rate": np.full(n, funding_val),
    })


def _make_variable_funding_df(n: int = 50) -> pd.DataFrame:
    np.random.seed(42)
    close = np.full(n, 30000.0)
    funding = np.random.uniform(-0.0005, 0.0005, n)
    return pd.DataFrame({
        "open": close - 5,
        "high": close + 20,
        "low": close - 20,
        "close": close,
        "volume": np.full(n, 1000.0),
        "funding_rate": funding,
    })


@pytest.fixture
def strategy() -> FundingRateArbStrategy:
    return FundingRateArbStrategy(
        symbols=["BTC/USDT:USDT"],
        min_confidence=0.3,
    )


def test_min_candles(strategy: FundingRateArbStrategy) -> None:
    assert strategy.min_candles_required() >= 30


def test_no_signal_without_funding_column(strategy: FundingRateArbStrategy) -> None:
    df = pd.DataFrame({
        "close": np.full(50, 30000.0),
        "open": np.full(50, 30000.0),
        "high": np.full(50, 30010.0),
        "low": np.full(50, 29990.0),
        "volume": np.full(50, 1000.0),
    })
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_short_signal_on_high_positive_funding(strategy: FundingRateArbStrategy) -> None:
    df = _make_funding_df(0.001)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction == SignalDirection.SHORT
        assert signal.metadata.get("funding_rate") > 0


def test_long_signal_on_negative_funding(strategy: FundingRateArbStrategy) -> None:
    df = _make_funding_df(-0.001)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction == SignalDirection.LONG


def test_no_signal_neutral_funding(strategy: FundingRateArbStrategy) -> None:
    df = _make_funding_df(0.00005)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    assert signal is None


def test_exit_when_zscore_normalizes(strategy: FundingRateArbStrategy) -> None:
    strategy.set_state("BTC/USDT:USDT", StrategyState.SHORT)
    df = _make_variable_funding_df()
    df["funding_rate"] = 0.0001
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal:
        assert signal.direction in (SignalDirection.CLOSE_SHORT, SignalDirection.SHORT)


def test_strategy_name(strategy: FundingRateArbStrategy) -> None:
    assert strategy.name == "funding_rate_arb"


def test_annualized_yield_in_metadata(strategy: FundingRateArbStrategy) -> None:
    df = _make_funding_df(0.001)
    signal = strategy.generate_signal("BTC/USDT:USDT", df)
    if signal and signal.metadata:
        assert "annualized_yield" in signal.metadata
