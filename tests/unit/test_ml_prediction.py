import numpy as np
import pandas as pd
import pytest

from ml.features import MLFeatureEngineer
from ml.prediction import PredictionResult, PredictionService
from ml.training import ModelTrainer, TargetBuilder


def _trained_model() -> tuple:
    np.random.seed(42)
    n = 500
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

    trainer = ModelTrainer("xgboost")
    trainer.create_model({"n_estimators": 20, "max_depth": 3})
    trainer.train(x, y)
    return trainer.model, list(x.columns), df


class TestPredictionResult:
    def test_confident_high(self) -> None:
        pr = PredictionResult("long", 0.85, 0.7, 30)
        assert pr.is_confident is True

    def test_not_confident_low(self) -> None:
        pr = PredictionResult("neutral", 0.5, 0.1, 30)
        assert pr.is_confident is False

    def test_threshold_exact(self) -> None:
        pr = PredictionResult("long", 0.8, 0.6, 20)
        assert pr.is_confident is True


class TestPredictionService:
    def test_predict_returns_result(self) -> None:
        model, features, df = _trained_model()
        svc = PredictionService(model, features)
        result = svc.predict(df)
        assert isinstance(result, PredictionResult)
        assert result.direction in ("long", "short", "neutral")
        assert 0 <= result.probability <= 1
        assert 0 <= result.confidence <= 1
        assert result.features_used > 0

    def test_predict_direction_not_neutral_with_data(self) -> None:
        model, features, df = _trained_model()
        svc = PredictionService(model, features)
        result = svc.predict(df)
        assert result.direction in ("long", "short")

    def test_predict_with_empty_features(self) -> None:
        model, _, df = _trained_model()
        svc = PredictionService(model, ["nonexistent_feature_xyz"])
        result = svc.predict(df)
        assert result.features_used == 0
        assert result.direction == "neutral"

    def test_predict_batch(self) -> None:
        model, features, df = _trained_model()
        svc = PredictionService(model, features)
        results = svc.predict_batch(df, step=50)
        assert len(results) > 0
        for r in results:
            assert isinstance(r, PredictionResult)
            assert r.direction in ("long", "short", "neutral")

    def test_confidence_threshold_property(self) -> None:
        model, features, _ = _trained_model()
        svc = PredictionService(model, features, confidence_threshold=0.7)
        assert svc.confidence_threshold == 0.7
