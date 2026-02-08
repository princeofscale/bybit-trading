import numpy as np
import pandas as pd
import pytest

from ml.features import MLFeatureEngineer, get_all_feature_names
from ml.training import ModelTrainer, TargetBuilder


def _make_dataset(n: int = 500) -> tuple[pd.DataFrame, pd.Series]:
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": close + np.random.randn(n) * 0.3,
        "high": close + np.abs(np.random.randn(n)) * 1.5,
        "low": close - np.abs(np.random.randn(n)) * 1.5,
        "close": close,
        "volume": np.random.uniform(100, 10000, n),
    })

    fe = MLFeatureEngineer()
    featured = fe.build_features(df)
    cleaned = fe.clean_features(featured)

    tb = TargetBuilder()
    target = tb.binary_direction(df, horizon=1)

    valid = target.notna()
    x = cleaned[valid]
    y = target[valid].astype(int)
    return x, y


class TestTargetBuilder:
    def test_binary_direction(self) -> None:
        df = pd.DataFrame({"close": [100, 102, 101, 105, 103]})
        tb = TargetBuilder()
        target = tb.binary_direction(df, horizon=1)
        assert target.iloc[0] == 1
        assert target.iloc[1] == 0
        assert target.iloc[2] == 1
        assert target.iloc[3] == 0
        assert target.iloc[4] == 0

    def test_forward_return(self) -> None:
        df = pd.DataFrame({"close": [100.0, 110.0, 105.0]})
        tb = TargetBuilder()
        ret = tb.forward_return(df, horizon=1)
        assert abs(ret.iloc[0] - 0.1) < 1e-10
        assert pd.isna(ret.iloc[2])

    def test_risk_adjusted_return(self) -> None:
        np.random.seed(42)
        df = pd.DataFrame({"close": 100 + np.cumsum(np.random.randn(100) * 0.5)})
        tb = TargetBuilder()
        rar = tb.risk_adjusted_return(df, horizon=5, vol_window=20)
        valid = rar.dropna()
        assert len(valid) > 0


class TestModelTrainerXGBoost:
    def test_create_model(self) -> None:
        trainer = ModelTrainer("xgboost")
        model = trainer.create_model()
        assert model is not None
        assert trainer.model is model

    def test_train_and_predict(self) -> None:
        x, y = _make_dataset()
        trainer = ModelTrainer("xgboost")
        trainer.create_model({"n_estimators": 10, "max_depth": 3})
        trainer.train(x, y)
        proba = trainer.predict_proba(x.iloc[:10])
        assert proba.shape == (10, 2)
        assert all(0 <= p <= 1 for row in proba for p in row)

    def test_feature_importance(self) -> None:
        x, y = _make_dataset()
        trainer = ModelTrainer("xgboost")
        trainer.create_model({"n_estimators": 10})
        trainer.train(x, y)
        imp = trainer.feature_importance()
        assert len(imp) == len(x.columns)
        assert all(isinstance(v, float) for v in imp.values())

    def test_predict_before_train_raises(self) -> None:
        trainer = ModelTrainer("xgboost")
        with pytest.raises(RuntimeError, match="model_not_trained"):
            trainer.predict_proba(pd.DataFrame({"a": [1]}))


class TestModelTrainerLightGBM:
    def test_create_lgbm(self) -> None:
        trainer = ModelTrainer("lightgbm")
        model = trainer.create_model()
        assert model is not None

    def test_train_lgbm(self) -> None:
        x, y = _make_dataset()
        trainer = ModelTrainer("lightgbm")
        trainer.create_model({"n_estimators": 10, "max_depth": 3})
        trainer.train(x, y)
        proba = trainer.predict_proba(x.iloc[:5])
        assert proba.shape == (5, 2)


class TestInvalidModelType:
    def test_raises_on_unknown(self) -> None:
        trainer = ModelTrainer("random_forest_xyz")
        with pytest.raises(ValueError, match="unknown_model_type"):
            trainer.create_model()


class TestWalkForwardCV:
    def test_returns_folds(self) -> None:
        x, y = _make_dataset(300)
        trainer = ModelTrainer("xgboost")
        trainer.create_model({"n_estimators": 10, "max_depth": 3})
        results = trainer.walk_forward_cv(x, y, n_splits=3)
        assert len(results) == 3
        for fold in results:
            assert "accuracy" in fold
            assert "log_loss" in fold
            assert 0 <= fold["accuracy"] <= 1
            assert fold["log_loss"] > 0
