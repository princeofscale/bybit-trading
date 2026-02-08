from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from ml.features import MLFeatureEngineer, get_all_feature_names


class TargetBuilder:
    def binary_direction(self, df: pd.DataFrame, horizon: int = 1) -> pd.Series:
        future_return = df["close"].pct_change(horizon).shift(-horizon)
        return (future_return > 0).astype(int)

    def forward_return(self, df: pd.DataFrame, horizon: int = 1) -> pd.Series:
        return df["close"].pct_change(horizon).shift(-horizon)

    def risk_adjusted_return(
        self, df: pd.DataFrame, horizon: int = 5, vol_window: int = 20,
    ) -> pd.Series:
        fwd = df["close"].pct_change(horizon).shift(-horizon)
        vol = df["close"].pct_change().rolling(vol_window).std()
        return fwd / vol.replace(0, np.nan)


class ModelTrainer:
    def __init__(self, model_type: str = "xgboost") -> None:
        self._model_type = model_type
        self._model: Any = None
        self._feature_names: list[str] = []

    @property
    def model(self) -> Any:
        return self._model

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    def create_model(self, params: dict[str, Any] | None = None) -> Any:
        if self._model_type == "xgboost":
            import xgboost as xgb
            defaults = {
                "n_estimators": 100,
                "max_depth": 5,
                "learning_rate": 0.1,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": 42,
                "eval_metric": "logloss",
            }
            if params:
                defaults.update(params)
            self._model = xgb.XGBClassifier(**defaults)
        elif self._model_type == "lightgbm":
            import lightgbm as lgb
            defaults = {
                "n_estimators": 100,
                "max_depth": 5,
                "learning_rate": 0.1,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": 42,
                "verbosity": -1,
            }
            if params:
                defaults.update(params)
            self._model = lgb.LGBMClassifier(**defaults)
        else:
            raise ValueError(f"unknown_model_type: {self._model_type}")
        return self._model

    def train(
        self, x: pd.DataFrame, y: pd.Series, feature_names: list[str] | None = None,
    ) -> Any:
        if self._model is None:
            self.create_model()
        self._feature_names = feature_names or list(x.columns)
        self._model.fit(x[self._feature_names], y)
        return self._model

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("model_not_trained")
        return self._model.predict_proba(x[self._feature_names])

    def feature_importance(self) -> dict[str, float]:
        if self._model is None:
            raise RuntimeError("model_not_trained")
        importances = self._model.feature_importances_
        return dict(zip(self._feature_names, importances.tolist()))

    def walk_forward_cv(
        self, x: pd.DataFrame, y: pd.Series, n_splits: int = 5,
    ) -> list[dict[str, float]]:
        from sklearn.metrics import accuracy_score, log_loss

        tscv = TimeSeriesSplit(n_splits=n_splits)
        results: list[dict[str, float]] = []

        for train_idx, test_idx in tscv.split(x):
            x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            if self._model is None:
                self.create_model()
            else:
                self.create_model()

            self._feature_names = list(x.columns)
            self._model.fit(x_train, y_train)

            proba = self._model.predict_proba(x_test)
            preds = self._model.predict(x_test)

            acc = accuracy_score(y_test, preds)
            ll = log_loss(y_test, proba, labels=[0, 1])
            results.append({"accuracy": acc, "log_loss": ll, "n_test": len(y_test)})

        return results
