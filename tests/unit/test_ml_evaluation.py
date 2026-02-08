import numpy as np
import pytest

from ml.evaluation import ClassificationMetrics, ModelEvaluator


@pytest.fixture
def evaluator() -> ModelEvaluator:
    return ModelEvaluator()


class TestEvaluate:
    def test_perfect_predictions(self, evaluator: ModelEvaluator) -> None:
        y_true = np.array([0, 0, 1, 1, 1])
        y_pred = np.array([0, 0, 1, 1, 1])
        proba = np.array([
            [0.9, 0.1], [0.8, 0.2],
            [0.1, 0.9], [0.2, 0.8], [0.15, 0.85],
        ])
        m = evaluator.evaluate(y_true, y_pred, proba)
        assert m.accuracy == 1.0
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.auc_roc == 1.0

    def test_all_wrong(self, evaluator: ModelEvaluator) -> None:
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([1, 1, 0, 0])
        m = evaluator.evaluate(y_true, y_pred)
        assert m.accuracy == 0.0

    def test_mixed_predictions(self, evaluator: ModelEvaluator) -> None:
        y_true = np.array([0, 0, 1, 1, 0, 1])
        y_pred = np.array([0, 1, 1, 0, 0, 1])
        m = evaluator.evaluate(y_true, y_pred)
        assert m.accuracy == pytest.approx(4 / 6)
        assert m.confusion is not None
        assert len(m.confusion) == 2

    def test_without_proba(self, evaluator: ModelEvaluator) -> None:
        y_true = np.array([0, 1, 1])
        y_pred = np.array([0, 1, 0])
        m = evaluator.evaluate(y_true, y_pred)
        assert m.auc_roc == 0.0
        assert m.log_loss_val == 0.0


class TestToDict:
    def test_has_all_keys(self) -> None:
        m = ClassificationMetrics(
            accuracy=0.8, precision=0.75, recall=0.9,
            auc_roc=0.85, log_loss_val=0.4,
        )
        d = m.to_dict()
        assert d["accuracy"] == 0.8
        assert d["precision"] == 0.75
        assert d["recall"] == 0.9
        assert d["auc_roc"] == 0.85
        assert d["log_loss"] == 0.4


class TestEvaluateByConfidence:
    def test_higher_threshold_fewer_samples(self, evaluator: ModelEvaluator) -> None:
        np.random.seed(42)
        n = 200
        y_true = np.random.randint(0, 2, n)
        proba = np.column_stack([
            1 - np.random.uniform(0.2, 0.8, n),
            np.random.uniform(0.2, 0.8, n),
        ])
        proba[:, 0] = 1 - proba[:, 1]

        results = evaluator.evaluate_by_confidence(
            y_true, proba, thresholds=[0.5, 0.6, 0.7],
        )
        assert len(results) == 3
        assert results[0]["n_samples"] >= results[1]["n_samples"]
        assert results[1]["n_samples"] >= results[2]["n_samples"]

    def test_coverage_decreases(self, evaluator: ModelEvaluator) -> None:
        np.random.seed(42)
        y_true = np.random.randint(0, 2, 100)
        proba = np.column_stack([
            np.random.uniform(0.3, 0.7, 100),
            np.random.uniform(0.3, 0.7, 100),
        ])
        proba[:, 0] = 1 - proba[:, 1]

        results = evaluator.evaluate_by_confidence(
            y_true, proba, thresholds=[0.5, 0.6, 0.7],
        )
        coverages = [r["coverage"] for r in results if r["n_samples"] > 0]
        for i in range(1, len(coverages)):
            assert coverages[i] <= coverages[i - 1]
