import numpy as np
import pandas as pd
import pytest

from core.orchestrator_execution import OrchestratorExecutionMixin


def _make_df(n: int = 250) -> pd.DataFrame:
    np.random.seed(42)
    close = np.cumsum(np.random.randn(n)) + 50000
    return pd.DataFrame({
        "open": close - 10,
        "high": close + 50,
        "low": close - 50,
        "close": close,
        "volume": np.random.randint(100, 5000, n).astype(float),
    })


class TestExtractMlFeatures:
    def setup_method(self) -> None:
        self._mixin = OrchestratorExecutionMixin()

    def test_extract_returns_features(self) -> None:
        df = _make_df()
        result = self._mixin._extract_ml_features(df)
        assert result is not None
        assert isinstance(result, dict)
        assert "rsi_14" in result
        assert "ema_9" in result
        assert "atr_14" in result
        assert len(result) > 30

    def test_extract_none_input(self) -> None:
        result = self._mixin._extract_ml_features(None)
        assert result is None

    def test_extract_empty_df(self) -> None:
        result = self._mixin._extract_ml_features(pd.DataFrame())
        assert result is None

    def test_extract_non_dataframe(self) -> None:
        result = self._mixin._extract_ml_features("not a dataframe")
        assert result is None

    def test_all_values_are_float(self) -> None:
        df = _make_df()
        result = self._mixin._extract_ml_features(df)
        assert result is not None
        for v in result.values():
            assert isinstance(v, float)
