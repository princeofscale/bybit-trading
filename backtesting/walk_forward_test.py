from decimal import Decimal

import pandas as pd
import structlog

from backtesting.backtester import Backtester
from backtesting.data_loader import BacktestDataLoader
from backtesting.models import BacktestConfig, BacktestResult, PerformanceMetrics
from backtesting.report_generator import ReportGenerator
from strategies.base_strategy import BaseStrategy, StrategyState

logger = structlog.get_logger("walk_forward")


class WalkForwardResult:
    def __init__(self) -> None:
        self.fold_results: list[BacktestResult] = []
        self.fold_metrics: list[PerformanceMetrics] = []
        self.aggregate_metrics: PerformanceMetrics = PerformanceMetrics()
        self.is_robust: bool = False

    @property
    def n_folds(self) -> int:
        return len(self.fold_results)

    @property
    def profitable_folds(self) -> int:
        return sum(1 for m in self.fold_metrics if m.total_return_pct > 0)

    @property
    def consistency_ratio(self) -> Decimal:
        if not self.fold_metrics:
            return Decimal("0")
        return Decimal(str(self.profitable_folds)) / Decimal(str(self.n_folds))


class WalkForwardTester:
    def __init__(self, config: BacktestConfig, n_splits: int = 5) -> None:
        self._config = config
        self._n_splits = n_splits
        self._loader = BacktestDataLoader()
        self._report = ReportGenerator()

    def run(
        self,
        strategy_factory: callable,
        symbol: str,
        df: pd.DataFrame,
        train_pct: float = 0.7,
    ) -> WalkForwardResult:
        splits = self._loader.split_walk_forward(df, self._n_splits, train_pct)
        wf_result = WalkForwardResult()

        for i, (train_df, test_df) in enumerate(splits):
            strategy = strategy_factory()
            strategy.set_state(symbol, StrategyState.IDLE)

            backtester = Backtester(self._config)
            result = backtester.run(strategy, symbol, test_df)
            metrics = self._report.calculate_metrics(result)
            result.metrics = metrics

            wf_result.fold_results.append(result)
            wf_result.fold_metrics.append(metrics)

        wf_result.aggregate_metrics = self._aggregate_metrics(wf_result)
        wf_result.is_robust = self._check_robustness(wf_result)

        return wf_result

    def _aggregate_metrics(self, wf: WalkForwardResult) -> PerformanceMetrics:
        if not wf.fold_metrics:
            return PerformanceMetrics()

        n = Decimal(str(len(wf.fold_metrics)))

        avg_return = sum(m.total_return_pct for m in wf.fold_metrics) / n
        avg_sharpe = sum(m.sharpe_ratio for m in wf.fold_metrics) / n
        avg_sortino = sum(m.sortino_ratio for m in wf.fold_metrics) / n
        max_dd = max(m.max_drawdown_pct for m in wf.fold_metrics)
        avg_win_rate = sum(m.win_rate for m in wf.fold_metrics) / n
        avg_pf = sum(m.profit_factor for m in wf.fold_metrics) / n
        total_trades = sum(m.total_trades for m in wf.fold_metrics)

        return PerformanceMetrics(
            total_return_pct=avg_return,
            sharpe_ratio=avg_sharpe,
            sortino_ratio=avg_sortino,
            max_drawdown_pct=max_dd,
            win_rate=avg_win_rate,
            profit_factor=avg_pf,
            total_trades=total_trades,
        )

    def _check_robustness(self, wf: WalkForwardResult) -> bool:
        if wf.n_folds < 2:
            return False

        if wf.consistency_ratio < Decimal("0.6"):
            return False

        if wf.aggregate_metrics.max_drawdown_pct > Decimal("0.30"):
            return False

        return True
