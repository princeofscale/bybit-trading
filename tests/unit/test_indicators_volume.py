import numpy as np
import pandas as pd
import pytest

from indicators.volume import (
    accumulation_distribution,
    chaikin_money_flow,
    cumulative_delta,
    delta_volume,
    ease_of_movement,
    force_index,
    mfi,
    obv,
    volume_profile,
    volume_ratio,
    volume_weighted_rsi,
    vwap,
)


@pytest.fixture
def sample_data() -> dict[str, pd.Series]:
    np.random.seed(42)
    n = 200
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    open_price = close.shift(1).fillna(close.iloc[0])
    high = pd.concat([close, open_price], axis=1).max(axis=1) + np.abs(np.random.randn(n))
    low = pd.concat([close, open_price], axis=1).min(axis=1) - np.abs(np.random.randn(n))
    volume = pd.Series(np.random.randint(100, 10000, n).astype(float))
    return {"open": open_price, "close": close, "high": high, "low": low, "volume": volume}


def test_obv(sample_data: dict[str, pd.Series]) -> None:
    result = obv(sample_data["close"], sample_data["volume"])
    assert len(result) == len(sample_data["close"])


def test_vwap(sample_data: dict[str, pd.Series]) -> None:
    result = vwap(
        sample_data["high"], sample_data["low"],
        sample_data["close"], sample_data["volume"],
    )
    assert len(result) == len(sample_data["close"])


def test_mfi(sample_data: dict[str, pd.Series]) -> None:
    result = mfi(
        sample_data["high"], sample_data["low"],
        sample_data["close"], sample_data["volume"],
    )
    assert len(result) == len(sample_data["close"])
    assert result.max() <= 100.0
    assert result.min() >= 0.0


def test_accumulation_distribution(sample_data: dict[str, pd.Series]) -> None:
    result = accumulation_distribution(
        sample_data["high"], sample_data["low"],
        sample_data["close"], sample_data["volume"],
    )
    assert len(result) == len(sample_data["close"])


def test_chaikin_money_flow(sample_data: dict[str, pd.Series]) -> None:
    result = chaikin_money_flow(
        sample_data["high"], sample_data["low"],
        sample_data["close"], sample_data["volume"],
    )
    assert len(result) == len(sample_data["close"])


def test_force_index(sample_data: dict[str, pd.Series]) -> None:
    result = force_index(sample_data["close"], sample_data["volume"])
    assert len(result) == len(sample_data["close"])


def test_ease_of_movement(sample_data: dict[str, pd.Series]) -> None:
    result = ease_of_movement(
        sample_data["high"], sample_data["low"], sample_data["volume"],
    )
    assert len(result) == len(sample_data["volume"])


def test_volume_profile(sample_data: dict[str, pd.Series]) -> None:
    result = volume_profile(sample_data["close"], sample_data["volume"], bins=20)
    assert len(result) == 20
    assert "price" in result.columns
    assert "volume" in result.columns
    assert result["volume"].sum() > 0


def test_delta_volume(sample_data: dict[str, pd.Series]) -> None:
    result = delta_volume(sample_data["open"], sample_data["close"], sample_data["volume"])
    assert len(result) == len(sample_data["close"])


def test_cumulative_delta(sample_data: dict[str, pd.Series]) -> None:
    result = cumulative_delta(sample_data["open"], sample_data["close"], sample_data["volume"])
    assert len(result) == len(sample_data["close"])


def test_volume_ratio(sample_data: dict[str, pd.Series]) -> None:
    result = volume_ratio(sample_data["volume"])
    assert len(result) == len(sample_data["volume"])
    assert not result.isna().any()


def test_volume_weighted_rsi(sample_data: dict[str, pd.Series]) -> None:
    result = volume_weighted_rsi(sample_data["close"], sample_data["volume"])
    assert len(result) == len(sample_data["close"])
    assert not result.isna().any()
