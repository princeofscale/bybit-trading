from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from ml.features import MLFeatureEngineer


class PredictionResult:
    def __init__(
        self,
        direction: str,
        probability: float,
        confidence: float,
        features_used: int,
    ) -> None:
        self.direction = direction
        self.probability = probability
        self.confidence = confidence
        self.features_used = features_used

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.6


class PredictionService:
    def __init__(
        self,
        model: Any,
        feature_names: list[str],
        confidence_threshold: float = 0.6,
    ) -> None:
        self._model = model
        self._feature_names = feature_names
        self._threshold = confidence_threshold
        self._feature_engineer = MLFeatureEngineer()

    def predict(self, df: pd.DataFrame) -> PredictionResult:
        featured = self._feature_engineer.build_features(df)
        cleaned = self._feature_engineer.clean_features(featured)

        available = [f for f in self._feature_names if f in cleaned.columns]
        if not available:
            return PredictionResult("neutral", 0.5, 0.0, 0)

        row = cleaned[available].iloc[[-1]]

        for col in self._feature_names:
            if col not in row.columns:
                row[col] = 0.0

        row = row[self._feature_names]
        proba = self._model.predict_proba(row)[0]

        prob_up = float(proba[1]) if len(proba) > 1 else 0.5
        prob_down = float(proba[0]) if len(proba) > 1 else 0.5

        confidence = abs(prob_up - 0.5) * 2

        if prob_up > 0.5:
            direction = "long"
        elif prob_down > 0.5:
            direction = "short"
        else:
            direction = "neutral"

        return PredictionResult(
            direction=direction,
            probability=prob_up,
            confidence=confidence,
            features_used=len(available),
        )

    def predict_batch(self, df: pd.DataFrame, step: int = 1) -> list[PredictionResult]:
        featured = self._feature_engineer.build_features(df)
        cleaned = self._feature_engineer.clean_features(featured)

        results: list[PredictionResult] = []
        min_rows = 50

        for i in range(min_rows, len(cleaned), step):
            window = cleaned.iloc[:i + 1]
            available = [f for f in self._feature_names if f in window.columns]
            if not available:
                results.append(PredictionResult("neutral", 0.5, 0.0, 0))
                continue

            row = window[available].iloc[[-1]]
            for col in self._feature_names:
                if col not in row.columns:
                    row[col] = 0.0
            row = row[self._feature_names]

            proba = self._model.predict_proba(row)[0]
            prob_up = float(proba[1]) if len(proba) > 1 else 0.5
            confidence = abs(prob_up - 0.5) * 2
            direction = "long" if prob_up > 0.5 else "short" if prob_up < 0.5 else "neutral"

            results.append(PredictionResult(
                direction=direction,
                probability=prob_up,
                confidence=confidence,
                features_used=len(available),
            ))

        return results

    @property
    def confidence_threshold(self) -> float:
        return self._threshold
