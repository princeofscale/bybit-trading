from decimal import Decimal

import pandas as pd
import pytest

from data.feature_engineer import FeatureEngineer
from data.preprocessor import CandlePreprocessor
from exchange.models import Candle


def _build_sample_df(count: int = 250) -> pd.DataFrame:
    candles = []
    base_price = 30000.0
    for i in range(count):
        price = base_price + (i % 50) * 10 - 250
        candles.append(Candle(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            open_time=i * 900_000,
            open=Decimal(str(price)),
            high=Decimal(str(price + 50)),
            low=Decimal(str(price - 50)),
            close=Decimal(str(price + 10)),
            volume=Decimal(str(1000 + i * 5)),
        ))
    preprocessor = CandlePreprocessor()
    return preprocessor.candles_to_dataframe(candles)


@pytest.fixture
def engineer() -> FeatureEngineer:
    return FeatureEngineer(fillna=True)


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return _build_sample_df()


def test_add_trend_indicators(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    result = engineer.add_trend_indicators(sample_df)
    for col in ["ema_9", "ema_21", "ema_50", "sma_20", "macd", "macd_signal", "macd_histogram", "adx"]:
        assert col in result.columns, f"Missing column: {col}"
    assert not result["ema_9"].isna().any()


def test_add_momentum_indicators(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    result = engineer.add_momentum_indicators(sample_df)
    for col in ["rsi_14", "rsi_7", "stoch_k", "stoch_d", "roc_10", "williams_r"]:
        assert col in result.columns, f"Missing column: {col}"


def test_add_volatility_indicators(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    result = engineer.add_volatility_indicators(sample_df)
    for col in ["bb_upper", "bb_middle", "bb_lower", "bb_width", "atr_14", "atr_7", "kc_upper", "kc_lower"]:
        assert col in result.columns, f"Missing column: {col}"


def test_add_volume_indicators(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    result = engineer.add_volume_indicators(sample_df)
    for col in ["obv", "vwap", "mfi_14", "adi", "volume_sma_20", "volume_ratio"]:
        assert col in result.columns, f"Missing column: {col}"


def test_add_custom_features(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    result = engineer.add_trend_indicators(sample_df)
    result = engineer.add_custom_features(result)
    for col in ["price_range", "body_ratio", "returns_1", "returns_5", "volatility_10"]:
        assert col in result.columns, f"Missing column: {col}"


def test_build_features_complete(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    result = engineer.build_features(sample_df)
    feature_cols = engineer.get_feature_columns()
    for col in feature_cols:
        assert col in result.columns, f"Missing feature column: {col}"


def test_build_features_no_nans(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    result = engineer.build_features(sample_df)
    feature_cols = engineer.get_feature_columns()
    nan_counts = result[feature_cols].isna().sum()
    cols_with_nans = nan_counts[nan_counts > 0]
    assert cols_with_nans.empty, f"Columns with NaN: {cols_with_nans.to_dict()}"


def test_get_feature_columns(engineer: FeatureEngineer) -> None:
    cols = engineer.get_feature_columns()
    assert len(cols) > 30
    assert "rsi_14" in cols
    assert "macd" in cols
    assert "atr_14" in cols


def test_does_not_modify_original(engineer: FeatureEngineer, sample_df: pd.DataFrame) -> None:
    original_cols = list(sample_df.columns)
    engineer.build_features(sample_df)
    assert list(sample_df.columns) == original_cols
