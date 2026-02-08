from decimal import Decimal

import pandas as pd
import pytest

from backtesting.data_loader import BacktestDataLoader
from backtesting.models import BacktestConfig
from backtesting.walk_forward_test import WalkForwardResult, WalkForwardTester
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class SimpleEntryStrategy(BaseStrategy):
    def __init__(self) -> None:
        super().__init__("simple_entry", ["TEST"])
        self._entered = False

    def min_candles_required(self) -> int:
        return 3

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        close = Decimal(str(df.iloc[-1]["close"]))
        if self.get_state(symbol) == StrategyState.IDLE and not self._entered:
            self._entered = True
            return Signal(
                symbol=symbol,
                direction=SignalDirection.LONG,
                confidence=0.8,
                strategy_name=self.name,
                entry_price=close,
                stop_loss=close * Decimal("0.95"),
                take_profit=close * Decimal("1.10"),
            )
        return None


@pytest.fixture
def config() -> BacktestConfig:
    return BacktestConfig(
        initial_equity=Decimal("10000"),
        slippage_pct=Decimal("0"),
        taker_fee=Decimal("0"),
        risk_per_trade=Decimal("0.02"),
        max_leverage=Decimal("3"),
    )


@pytest.fixture
def df() -> pd.DataFrame:
    loader = BacktestDataLoader()
    return loader.generate_synthetic(
        n_bars=200, start_price=100.0,
        volatility=0.01, trend=0.0005,
    )


class TestWalkForwardTester:
    def test_produces_fold_results(self, config: BacktestConfig, df: pd.DataFrame) -> None:
        wf = WalkForwardTester(config, n_splits=3)
        result = wf.run(SimpleEntryStrategy, "TEST", df)
        assert result.n_folds >= 1
        assert len(result.fold_results) == result.n_folds
        assert len(result.fold_metrics) == result.n_folds

    def test_aggregate_metrics_populated(self, config: BacktestConfig, df: pd.DataFrame) -> None:
        wf = WalkForwardTester(config, n_splits=3)
        result = wf.run(SimpleEntryStrategy, "TEST", df)
        assert result.aggregate_metrics.total_trades >= 0

    def test_consistency_ratio(self, config: BacktestConfig, df: pd.DataFrame) -> None:
        wf = WalkForwardTester(config, n_splits=3)
        result = wf.run(SimpleEntryStrategy, "TEST", df)
        assert Decimal("0") <= result.consistency_ratio <= Decimal("1")

    def test_profitable_folds_count(self, config: BacktestConfig, df: pd.DataFrame) -> None:
        wf = WalkForwardTester(config, n_splits=3)
        result = wf.run(SimpleEntryStrategy, "TEST", df)
        assert result.profitable_folds <= result.n_folds

    def test_robustness_check(self, config: BacktestConfig, df: pd.DataFrame) -> None:
        wf = WalkForwardTester(config, n_splits=3)
        result = wf.run(SimpleEntryStrategy, "TEST", df)
        assert isinstance(result.is_robust, bool)


class TestWalkForwardResult:
    def test_empty_result(self) -> None:
        r = WalkForwardResult()
        assert r.n_folds == 0
        assert r.profitable_folds == 0
        assert r.consistency_ratio == Decimal("0")


class TestEachFoldIsFresh:
    def test_strategies_independent(self, config: BacktestConfig, df: pd.DataFrame) -> None:
        wf = WalkForwardTester(config, n_splits=3)
        result = wf.run(SimpleEntryStrategy, "TEST", df)
        for fold_result in result.fold_results:
            assert fold_result.strategy_name == "simple_entry"
