from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)


class ClassificationMetrics:
    def __init__(
        self,
        accuracy: float = 0.0,
        precision: float = 0.0,
        recall: float = 0.0,
        auc_roc: float = 0.0,
        log_loss_val: float = 0.0,
        confusion: list[list[int]] | None = None,
    ) -> None:
        self.accuracy = accuracy
        self.precision = precision
        self.recall = recall
        self.auc_roc = auc_roc
        self.log_loss_val = log_loss_val
        self.confusion = confusion or []

    def to_dict(self) -> dict[str, float]:
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "auc_roc": self.auc_roc,
            "log_loss": self.log_loss_val,
        }


class ModelEvaluator:
    def evaluate(
        self,
        y_true: np.ndarray | pd.Series,
        y_pred: np.ndarray,
        y_proba: np.ndarray | None = None,
    ) -> ClassificationMetrics:
        y_t = np.asarray(y_true)
        y_p = np.asarray(y_pred)

        acc = accuracy_score(y_t, y_p)
        prec = precision_score(y_t, y_p, zero_division=0)
        rec = recall_score(y_t, y_p, zero_division=0)

        auc = 0.0
        ll = 0.0
        if y_proba is not None:
            try:
                auc = roc_auc_score(y_t, y_proba[:, 1])
            except (ValueError, IndexError):
                auc = 0.0
            try:
                ll = log_loss(y_t, y_proba, labels=[0, 1])
            except ValueError:
                ll = 0.0

        cm = confusion_matrix(y_t, y_p).tolist()

        return ClassificationMetrics(
            accuracy=acc,
            precision=prec,
            recall=rec,
            auc_roc=auc,
            log_loss_val=ll,
            confusion=cm,
        )

    def evaluate_by_confidence(
        self,
        y_true: np.ndarray | pd.Series,
        y_proba: np.ndarray,
        thresholds: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        if thresholds is None:
            thresholds = [0.5, 0.55, 0.6, 0.65, 0.7]

        y_t = np.asarray(y_true)
        results: list[dict[str, Any]] = []

        for thresh in thresholds:
            confidence = np.abs(y_proba[:, 1] - 0.5) * 2
            mask = confidence >= (thresh - 0.5) * 2

            if mask.sum() == 0:
                results.append({
                    "threshold": thresh,
                    "n_samples": 0,
                    "accuracy": 0.0,
                    "coverage": 0.0,
                })
                continue

            y_filtered = y_t[mask]
            pred_filtered = (y_proba[:, 1][mask] >= 0.5).astype(int)

            acc = accuracy_score(y_filtered, pred_filtered)
            coverage = mask.sum() / len(y_t)

            results.append({
                "threshold": thresh,
                "n_samples": int(mask.sum()),
                "accuracy": acc,
                "coverage": coverage,
            })

        return results
