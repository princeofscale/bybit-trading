import numpy as np
import pandas as pd
import pytest

from indicators.volatility import (
    atr,
    bollinger_bands,
    donchian_channel,
    garman_klass_volatility,
    keltner_channel,
    parkinson_volatility,
    realized_volatility,
    squeeze_momentum,
    volatility_regime,
)


@pytest.fixture
def sample_data() -> dict[str, pd.Series]:
    np.random.seed(42)
    n = 200
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    open_price = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([close, open_price], axis=1).max(axis=1) + np.abs(np.random.randn(n))
    low = pd.concat([close, open_price], axis=1).min(axis=1) - np.abs(np.random.randn(n))
    return {"open": open_price, "close": close, "high": high, "low": low}


def test_atr(sample_data: dict[str, pd.Series]) -> None:
    result = atr(sample_data["high"], sample_data["low"], sample_data["close"])
    assert len(result) == len(sample_data["close"])
    assert (result >= 0).all()


def test_bollinger_bands(sample_data: dict[str, pd.Series]) -> None:
    result = bollinger_bands(sample_data["close"])
    assert "upper" in result
    assert "middle" in result
    assert "lower" in result
    assert "width" in result
    assert "pct_b" in result


def test_keltner_channel(sample_data: dict[str, pd.Series]) -> None:
    result = keltner_channel(
        sample_data["high"], sample_data["low"], sample_data["close"],
    )
    assert "upper" in result
    assert "middle" in result
    assert "lower" in result


def test_donchian_channel(sample_data: dict[str, pd.Series]) -> None:
    result = donchian_channel(
        sample_data["high"], sample_data["low"], sample_data["close"],
    )
    assert "upper" in result
    assert "lower" in result
    assert "width" in result


def test_realized_volatility(sample_data: dict[str, pd.Series]) -> None:
    result = realized_volatility(sample_data["close"], window=20)
    assert len(result) == len(sample_data["close"])
    assert (result >= 0).all()


def test_parkinson_volatility(sample_data: dict[str, pd.Series]) -> None:
    result = parkinson_volatility(sample_data["high"], sample_data["low"])
    assert len(result) == len(sample_data["high"])
    assert (result >= 0).all()


def test_garman_klass_volatility(sample_data: dict[str, pd.Series]) -> None:
    result = garman_klass_volatility(
        sample_data["open"], sample_data["high"],
        sample_data["low"], sample_data["close"],
    )
    assert len(result) == len(sample_data["close"])
    assert (result >= 0).all()


def test_volatility_regime(sample_data: dict[str, pd.Series]) -> None:
    result = volatility_regime(sample_data["close"], short_window=10, long_window=60)
    assert len(result) == len(sample_data["close"])
    assert not result.isna().any()


def test_squeeze_momentum(sample_data: dict[str, pd.Series]) -> None:
    squeeze_on, momentum = squeeze_momentum(
        sample_data["high"], sample_data["low"], sample_data["close"],
    )
    assert len(squeeze_on) == len(sample_data["close"])
    assert set(squeeze_on.unique()).issubset({0, 1})
