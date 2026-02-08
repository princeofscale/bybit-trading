import numpy as np
import pandas as pd
import pytest

from ml.walk_forward import WalkForwardML, WalkForwardMLResult


def _make_df(n: int = 600) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.3,
        "high": close + np.abs(np.random.randn(n)) * 1.5,
        "low": close - np.abs(np.random.randn(n)) * 1.5,
        "close": close,
        "volume": np.random.uniform(100, 10000, n),
    })


class TestWalkForwardML:
    def test_produces_folds(self) -> None:
        wf = WalkForwardML(
            model_type="xgboost", n_splits=3,
            model_params={"n_estimators": 10, "max_depth": 3},
        )
        result = wf.run(_make_df(), target_horizon=1)
        assert result.n_folds == 3

    def test_each_fold_has_metrics(self) -> None:
        wf = WalkForwardML(
            model_type="xgboost", n_splits=3,
            model_params={"n_estimators": 10, "max_depth": 3},
        )
        result = wf.run(_make_df(), target_horizon=1)
        for fold in result.folds:
            assert 0 <= fold.metrics.accuracy <= 1
            assert fold.train_size > 0
            assert fold.test_size > 0

    def test_avg_accuracy_computed(self) -> None:
        wf = WalkForwardML(
            model_type="xgboost", n_splits=3,
            model_params={"n_estimators": 10, "max_depth": 3},
        )
        result = wf.run(_make_df(), target_horizon=1)
        assert 0 <= result.avg_accuracy <= 1
        assert result.std_accuracy >= 0

    def test_overfit_detection_is_bool(self) -> None:
        wf = WalkForwardML(
            model_type="xgboost", n_splits=4,
            model_params={"n_estimators": 10, "max_depth": 3},
        )
        result = wf.run(_make_df(), target_horizon=1)
        assert isinstance(result.is_overfit, (bool, np.bool_))

    def test_best_fold_valid(self) -> None:
        wf = WalkForwardML(
            model_type="xgboost", n_splits=3,
            model_params={"n_estimators": 10, "max_depth": 3},
        )
        result = wf.run(_make_df(), target_horizon=1)
        assert 0 <= result.best_fold_idx < result.n_folds


class TestWalkForwardLightGBM:
    def test_lgbm_works(self) -> None:
        wf = WalkForwardML(
            model_type="lightgbm", n_splits=3,
            model_params={"n_estimators": 10, "max_depth": 3, "verbosity": -1},
        )
        result = wf.run(_make_df(), target_horizon=1)
        assert result.n_folds == 3
        assert 0 <= result.avg_accuracy <= 1


class TestEmptyResult:
    def test_default_result(self) -> None:
        r = WalkForwardMLResult()
        assert r.n_folds == 0
        assert r.avg_accuracy == 0.0
        assert r.is_overfit is False
