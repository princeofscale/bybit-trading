import numpy as np
import pandas as pd
import pytest

from indicators.momentum import (
    awesome_oscillator,
    cci,
    momentum_score,
    roc,
    rsi,
    stochastic,
    tsi,
    ultimate_oscillator,
    williams_r,
)


@pytest.fixture
def sample_data() -> dict[str, pd.Series]:
    np.random.seed(42)
    n = 200
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    high = close + np.abs(np.random.randn(n)) * 2
    low = close - np.abs(np.random.randn(n)) * 2
    volume = pd.Series(np.random.randint(100, 10000, n).astype(float))
    return {"close": close, "high": high, "low": low, "volume": volume}


def test_rsi(sample_data: dict[str, pd.Series]) -> None:
    result = rsi(sample_data["close"], window=14)
    assert len(result) == len(sample_data["close"])
    assert result.max() <= 100.0
    assert result.min() >= 0.0


def test_stochastic(sample_data: dict[str, pd.Series]) -> None:
    k, d = stochastic(sample_data["high"], sample_data["low"], sample_data["close"])
    assert len(k) == len(sample_data["close"])
    assert len(d) == len(sample_data["close"])


def test_roc(sample_data: dict[str, pd.Series]) -> None:
    result = roc(sample_data["close"], window=10)
    assert len(result) == len(sample_data["close"])


def test_williams_r(sample_data: dict[str, pd.Series]) -> None:
    result = williams_r(sample_data["high"], sample_data["low"], sample_data["close"])
    assert len(result) == len(sample_data["close"])


def test_cci(sample_data: dict[str, pd.Series]) -> None:
    result = cci(sample_data["high"], sample_data["low"], sample_data["close"])
    assert len(result) == len(sample_data["close"])


def test_tsi(sample_data: dict[str, pd.Series]) -> None:
    result = tsi(sample_data["close"])
    assert len(result) == len(sample_data["close"])


def test_awesome_oscillator(sample_data: dict[str, pd.Series]) -> None:
    result = awesome_oscillator(sample_data["high"], sample_data["low"])
    assert len(result) == len(sample_data["high"])


def test_ultimate_oscillator(sample_data: dict[str, pd.Series]) -> None:
    result = ultimate_oscillator(
        sample_data["high"], sample_data["low"], sample_data["close"],
    )
    assert len(result) == len(sample_data["close"])


def test_momentum_score(sample_data: dict[str, pd.Series]) -> None:
    result = momentum_score(
        sample_data["close"], sample_data["high"], sample_data["low"],
    )
    assert len(result) == len(sample_data["close"])
    assert not result.isna().any()
