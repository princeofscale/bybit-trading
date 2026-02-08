import numpy as np
import pandas as pd
import pytest

from indicators.correlation import (
    beta,
    cointegration_spread,
    cross_asset_momentum,
    pair_distance,
    rolling_correlation,
)


@pytest.fixture
def two_series() -> tuple[pd.Series, pd.Series]:
    np.random.seed(42)
    n = 100
    a = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    b = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    return a, b


def test_rolling_correlation(two_series: tuple[pd.Series, pd.Series]) -> None:
    a, b = two_series
    result = rolling_correlation(a, b, window=20)
    assert len(result) == len(a)
    assert result.max() <= 1.0
    assert result.min() >= -1.0


def test_rolling_correlation_self(two_series: tuple[pd.Series, pd.Series]) -> None:
    a, _ = two_series
    result = rolling_correlation(a, a, window=20)
    non_zero = result[result != 0]
    assert (non_zero > 0.99).all()


def test_beta(two_series: tuple[pd.Series, pd.Series]) -> None:
    a, b = two_series
    ret_a = a.pct_change().fillna(0)
    ret_b = b.pct_change().fillna(0)
    result = beta(ret_a, ret_b, window=20)
    assert len(result) == len(a)


def test_cointegration_spread(two_series: tuple[pd.Series, pd.Series]) -> None:
    a, b = two_series
    ratio, zscore = cointegration_spread(a, b, window=30)
    assert len(ratio) == len(a)
    assert len(zscore) == len(a)
    assert not ratio.isna().any()
    assert not zscore.isna().any()


def test_cross_asset_momentum() -> None:
    np.random.seed(42)
    price_dict = {
        "BTC": pd.Series(np.cumsum(np.random.randn(100)) + 30000),
        "ETH": pd.Series(np.cumsum(np.random.randn(100)) + 2000),
        "SOL": pd.Series(np.cumsum(np.random.randn(100)) + 100),
    }
    result = cross_asset_momentum(price_dict, window=20)
    assert "BTC" in result.columns
    assert "ETH" in result.columns
    assert len(result) == 100


def test_pair_distance(two_series: tuple[pd.Series, pd.Series]) -> None:
    a, b = two_series
    result = pair_distance(a, b, window=30)
    assert len(result) == len(a)
    assert not result.isna().any()
