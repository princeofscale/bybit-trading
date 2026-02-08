import numpy as np
import pandas as pd
import pytest

from ml.features import FEATURE_GROUPS, MLFeatureEngineer, get_all_feature_names


def _make_ohlcv(n: int = 250) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.3,
        "high": close + np.abs(np.random.randn(n)) * 1.5,
        "low": close - np.abs(np.random.randn(n)) * 1.5,
        "close": close,
        "volume": np.random.uniform(100, 10000, n),
    })


@pytest.fixture
def fe() -> MLFeatureEngineer:
    return MLFeatureEngineer()


@pytest.fixture
def df() -> pd.DataFrame:
    return _make_ohlcv()


class TestFeatureGroups:
    def test_all_groups_present(self) -> None:
        assert set(FEATURE_GROUPS.keys()) == {
            "trend", "momentum", "volatility", "volume", "price_action",
        }

    def test_get_all_feature_names_non_empty(self) -> None:
        names = get_all_feature_names()
        assert len(names) > 30

    def test_no_duplicate_names(self) -> None:
        names = get_all_feature_names()
        assert len(names) == len(set(names))


class TestBuildFeatures:
    def test_adds_all_feature_columns(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        result = fe.build_features(df)
        expected = get_all_feature_names()
        for col in expected:
            assert col in result.columns, f"missing: {col}"

    def test_preserves_original_columns(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        result = fe.build_features(df)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns

    def test_output_length_same(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        result = fe.build_features(df)
        assert len(result) == len(df)

    def test_rsi_range(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        result = fe.build_features(df)
        valid = result["rsi_14"].dropna()
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_bb_pct_exists(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        result = fe.build_features(df)
        assert "bb_pct" in result.columns
        assert not result["bb_pct"].dropna().empty

    def test_returns_computed(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        result = fe.build_features(df)
        assert "return_1" in result.columns
        manual = df["close"].pct_change(1)
        pd.testing.assert_series_equal(result["return_1"], manual, check_names=False)


class TestCleanFeatures:
    def test_removes_inf(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        built = fe.build_features(df)
        cleaned = fe.clean_features(built)
        assert not np.isinf(cleaned.values).any()

    def test_no_nans(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        built = fe.build_features(df)
        cleaned = fe.clean_features(built)
        assert not cleaned.isna().any().any()

    def test_only_feature_columns(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        built = fe.build_features(df)
        cleaned = fe.clean_features(built)
        for col in cleaned.columns:
            assert col in get_all_feature_names()
        assert "open" not in cleaned.columns
        assert "close" not in cleaned.columns

    def test_shape_preserved(self, fe: MLFeatureEngineer, df: pd.DataFrame) -> None:
        built = fe.build_features(df)
        cleaned = fe.clean_features(built)
        assert len(cleaned) == len(df)
