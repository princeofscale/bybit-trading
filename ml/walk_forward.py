from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from ml.evaluation import ClassificationMetrics, ModelEvaluator
from ml.features import MLFeatureEngineer, get_all_feature_names
from ml.training import ModelTrainer, TargetBuilder


class WalkForwardFold:
    def __init__(
        self,
        fold_idx: int,
        train_size: int,
        test_size: int,
        metrics: ClassificationMetrics,
    ) -> None:
        self.fold_idx = fold_idx
        self.train_size = train_size
        self.test_size = test_size
        self.metrics = metrics


class WalkForwardMLResult:
    def __init__(self) -> None:
        self.folds: list[WalkForwardFold] = []
        self.avg_accuracy: float = 0.0
        self.avg_auc: float = 0.0
        self.std_accuracy: float = 0.0
        self.is_overfit: bool = False
        self.best_fold_idx: int = 0

    @property
    def n_folds(self) -> int:
        return len(self.folds)


class WalkForwardML:
    def __init__(
        self, model_type: str = "xgboost", n_splits: int = 5,
        model_params: dict[str, Any] | None = None,
    ) -> None:
        self._model_type = model_type
        self._n_splits = n_splits
        self._model_params = model_params
        self._evaluator = ModelEvaluator()

    def run(
        self,
        df: pd.DataFrame,
        target_horizon: int = 1,
        feature_names: list[str] | None = None,
    ) -> WalkForwardMLResult:
        fe = MLFeatureEngineer()
        featured = fe.build_features(df)

        tb = TargetBuilder()
        target = tb.binary_direction(featured, horizon=target_horizon)

        cleaned = fe.clean_features(featured)
        cols = feature_names or [c for c in get_all_feature_names() if c in cleaned.columns]
        x = cleaned[cols]

        valid_mask = target.notna()
        x = x[valid_mask]
        y = target[valid_mask].astype(int)

        tscv = TimeSeriesSplit(n_splits=self._n_splits)
        result = WalkForwardMLResult()
        best_acc = 0.0

        for i, (train_idx, test_idx) in enumerate(tscv.split(x)):
            x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            trainer = ModelTrainer(self._model_type)
            trainer.create_model(self._model_params)
            trainer.train(x_train, y_train, cols)

            proba = trainer.predict_proba(x_test)
            preds = (proba[:, 1] >= 0.5).astype(int)

            metrics = self._evaluator.evaluate(y_test, preds, proba)

            fold = WalkForwardFold(
                fold_idx=i,
                train_size=len(x_train),
                test_size=len(x_test),
                metrics=metrics,
            )
            result.folds.append(fold)

            if metrics.accuracy > best_acc:
                best_acc = metrics.accuracy
                result.best_fold_idx = i

        if result.folds:
            accs = [f.metrics.accuracy for f in result.folds]
            aucs = [f.metrics.auc_roc for f in result.folds]
            result.avg_accuracy = np.mean(accs)
            result.avg_auc = np.mean(aucs)
            result.std_accuracy = np.std(accs)

            first_half = accs[: len(accs) // 2]
            second_half = accs[len(accs) // 2:]
            if first_half and second_half:
                result.is_overfit = np.mean(first_half) > np.mean(second_half) + 0.05

        return result
