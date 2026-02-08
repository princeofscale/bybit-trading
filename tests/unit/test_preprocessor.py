from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from data.preprocessor import CandlePreprocessor
from exchange.models import Candle


def _make_candle(
    open_time: int,
    o: str = "100",
    h: str = "110",
    l: str = "90",
    c: str = "105",
    vol: str = "50",
) -> Candle:
    return Candle(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        open_time=open_time,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=Decimal(vol),
    )


@pytest.fixture
def preprocessor() -> CandlePreprocessor:
    return CandlePreprocessor()


def test_candles_to_dataframe(preprocessor: CandlePreprocessor) -> None:
    candles = [_make_candle(1000), _make_candle(2000)]
    df = preprocessor.candles_to_dataframe(candles)
    assert len(df) == 2
    assert list(df.columns) == [
        "open_time", "open", "high", "low", "close", "volume", "symbol", "timeframe",
    ]


def test_candles_to_dataframe_empty(preprocessor: CandlePreprocessor) -> None:
    df = preprocessor.candles_to_dataframe([])
    assert df.empty


def test_candles_to_dataframe_sorted(preprocessor: CandlePreprocessor) -> None:
    candles = [_make_candle(2000), _make_candle(1000)]
    df = preprocessor.candles_to_dataframe(candles)
    assert df["open_time"].iloc[0] < df["open_time"].iloc[1]


def test_validate_ohlcv_removes_invalid(preprocessor: CandlePreprocessor) -> None:
    good = _make_candle(1000, o="100", h="110", l="90", c="105")
    bad_high = _make_candle(2000, o="100", h="95", l="90", c="105")
    candles = [good, bad_high]
    df = preprocessor.candles_to_dataframe(candles)
    result = preprocessor.validate_ohlcv(df)
    assert len(result) == 1


def test_validate_ohlcv_negative_volume(preprocessor: CandlePreprocessor) -> None:
    bad = _make_candle(1000, vol="-10")
    df = preprocessor.candles_to_dataframe([bad])
    result = preprocessor.validate_ohlcv(df)
    assert len(result) == 0


def test_validate_ohlcv_empty(preprocessor: CandlePreprocessor) -> None:
    df = preprocessor.candles_to_dataframe([])
    result = preprocessor.validate_ohlcv(df)
    assert result.empty


def test_detect_gaps(preprocessor: CandlePreprocessor) -> None:
    candles = [
        _make_candle(0),
        _make_candle(900_000),
        _make_candle(5_400_000),
    ]
    df = preprocessor.candles_to_dataframe(candles)
    gaps = preprocessor.detect_gaps(df, timeframe_ms=900_000)
    assert len(gaps) == 1


def test_detect_gaps_no_gaps(preprocessor: CandlePreprocessor) -> None:
    candles = [_make_candle(i * 900_000) for i in range(5)]
    df = preprocessor.candles_to_dataframe(candles)
    gaps = preprocessor.detect_gaps(df, timeframe_ms=900_000)
    assert len(gaps) == 0


def test_fill_missing_candles(preprocessor: CandlePreprocessor) -> None:
    candles = [
        _make_candle(0, c="100"),
        _make_candle(2 * 900_000, c="110"),
    ]
    df = preprocessor.candles_to_dataframe(candles)
    result = preprocessor.fill_missing_candles(df, timeframe_ms=900_000)
    assert len(result) == 3
    assert result["volume"].iloc[1] == 0.0


def test_remove_duplicates(preprocessor: CandlePreprocessor) -> None:
    candles = [
        _make_candle(1000, c="100"),
        _make_candle(1000, c="105"),
        _make_candle(2000, c="110"),
    ]
    df = preprocessor.candles_to_dataframe(candles)
    result = preprocessor.remove_duplicates(df)
    assert len(result) == 2


def test_normalize_returns(preprocessor: CandlePreprocessor) -> None:
    candles = [_make_candle(i * 900_000, c=str(100 + i * 5)) for i in range(5)]
    df = preprocessor.candles_to_dataframe(candles)
    result = preprocessor.normalize_returns(df)
    assert "returns" in result.columns
    assert "log_returns" in result.columns
    assert pd.isna(result["returns"].iloc[0])
    assert not pd.isna(result["returns"].iloc[1])


def test_clean_pipeline(preprocessor: CandlePreprocessor) -> None:
    candles = [
        _make_candle(i * 900_000, o=str(100 + i * 5), h=str(110 + i * 5), l=str(90 + i * 5), c=str(105 + i * 5))
        for i in range(10)
    ]
    result = preprocessor.clean_pipeline(candles, timeframe_ms=900_000)
    assert len(result) == 10
    assert "returns" in result.columns
    assert "log_returns" in result.columns
