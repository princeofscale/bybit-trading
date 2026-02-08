import numpy as np
import pandas as pd
import pytest

from indicators.on_chain import (
    funding_arb_signal,
    funding_rate_zscore,
    liquidation_intensity,
    long_short_ratio_signal,
    open_interest_change,
    open_interest_to_volume,
    whale_activity_score,
)


def test_funding_rate_zscore() -> None:
    rates = pd.Series(np.random.uniform(-0.001, 0.001, 100))
    result = funding_rate_zscore(rates, window=20)
    assert len(result) == 100
    assert not result.isna().any()


def test_open_interest_change() -> None:
    oi = pd.Series([100, 110, 105, 120, 115], dtype=float)
    result = open_interest_change(oi)
    assert len(result) == 5
    assert result.iloc[1] == pytest.approx(0.1, abs=0.001)


def test_open_interest_to_volume() -> None:
    oi = pd.Series([1000, 1100, 1200], dtype=float)
    vol = pd.Series([500, 600, 0], dtype=float)
    result = open_interest_to_volume(oi, vol)
    assert result.iloc[0] == pytest.approx(2.0)
    assert result.iloc[2] == 0.0


def test_long_short_ratio_signal() -> None:
    ratio = pd.Series([0.3, 0.5, 1.0, 2.0, 3.0])
    result = long_short_ratio_signal(ratio, overbought=2.0, oversold=0.5)
    assert result.iloc[0] == 1
    assert result.iloc[2] == 0
    assert result.iloc[4] == -1


def test_liquidation_intensity() -> None:
    liq_vol = pd.Series(np.random.uniform(0, 100, 50))
    total_vol = pd.Series(np.random.uniform(1000, 10000, 50))
    result = liquidation_intensity(liq_vol, total_vol, window=10)
    assert len(result) == 50
    assert (result >= 0).all()


def test_funding_arb_signal_positive() -> None:
    rates = pd.Series([0.0, 0.0004, 0.002, -0.0004, -0.002])
    result = funding_arb_signal(rates)
    assert result.iloc[0] == 0.0
    assert result.iloc[1] == -0.5
    assert result.iloc[2] == -1.0
    assert result.iloc[3] == 0.5
    assert result.iloc[4] == 1.0


def test_whale_activity_score() -> None:
    np.random.seed(42)
    volume = pd.Series(np.random.uniform(100, 1000, 100))
    volume.iloc[90] = 5000
    result = whale_activity_score(volume, avg_window=50)
    assert len(result) == 100
    assert result.iloc[90] > result.iloc[50]
    assert (result >= 0).all()
    assert (result <= 1).all()
