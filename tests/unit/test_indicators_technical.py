import numpy as np
import pandas as pd
import pytest

from indicators.technical import adx, ema, hull_ma, ichimoku, macd, pivot_points, sma, supertrend, wma


@pytest.fixture
def sample_data() -> dict[str, pd.Series]:
    np.random.seed(42)
    n = 200
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    high = close + np.abs(np.random.randn(n)) * 2
    low = close - np.abs(np.random.randn(n)) * 2
    return {"close": close, "high": high, "low": low}


def test_ema(sample_data: dict[str, pd.Series]) -> None:
    result = ema(sample_data["close"], window=20)
    assert len(result) == len(sample_data["close"])
    assert not result.isna().all()


def test_sma(sample_data: dict[str, pd.Series]) -> None:
    result = sma(sample_data["close"], window=20)
    assert len(result) == len(sample_data["close"])


def test_wma(sample_data: dict[str, pd.Series]) -> None:
    result = wma(sample_data["close"], window=10)
    assert len(result) == len(sample_data["close"])
    assert not result.iloc[-1:].isna().any()


def test_hull_ma(sample_data: dict[str, pd.Series]) -> None:
    result = hull_ma(sample_data["close"], window=16)
    assert len(result) == len(sample_data["close"])


def test_macd(sample_data: dict[str, pd.Series]) -> None:
    macd_line, signal_line, histogram = macd(sample_data["close"])
    assert len(macd_line) == len(sample_data["close"])
    assert len(signal_line) == len(sample_data["close"])
    assert len(histogram) == len(sample_data["close"])


def test_adx(sample_data: dict[str, pd.Series]) -> None:
    adx_val, adx_pos, adx_neg = adx(
        sample_data["high"], sample_data["low"], sample_data["close"],
    )
    assert len(adx_val) == len(sample_data["close"])
    assert not adx_val.isna().all()


def test_ichimoku(sample_data: dict[str, pd.Series]) -> None:
    result = ichimoku(sample_data["high"], sample_data["low"])
    assert "tenkan_sen" in result
    assert "kijun_sen" in result
    assert "senkou_a" in result
    assert "senkou_b" in result
    assert len(result["tenkan_sen"]) == len(sample_data["high"])


def test_supertrend(sample_data: dict[str, pd.Series]) -> None:
    st, direction = supertrend(
        sample_data["high"], sample_data["low"], sample_data["close"],
    )
    assert len(st) == len(sample_data["close"])
    assert set(direction.unique()).issubset({-1, 1})


def test_pivot_points(sample_data: dict[str, pd.Series]) -> None:
    result = pivot_points(sample_data["high"], sample_data["low"], sample_data["close"])
    assert "pivot" in result
    assert "r1" in result
    assert "s1" in result
    assert "r3" in result
    assert "s3" in result
