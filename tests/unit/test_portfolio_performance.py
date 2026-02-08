from decimal import Decimal

import pytest

from portfolio.performance import StrategyPerformance


@pytest.fixture
def perf() -> StrategyPerformance:
    return StrategyPerformance("test_strategy")


class TestRecordReturn:
    def test_increments_trade_count(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.05"))
        assert perf.total_trades == 1
        perf.record_return(Decimal("-0.02"))
        assert perf.total_trades == 2

    def test_counts_wins(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.05"))
        perf.record_return(Decimal("-0.02"))
        perf.record_return(Decimal("0.03"))
        assert perf.win_rate == Decimal("2") / Decimal("3")


class TestCumulativeReturn:
    def test_single_return(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.10"))
        assert perf.cumulative_return == Decimal("0.10")

    def test_compounding(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.10"))
        perf.record_return(Decimal("0.10"))
        expected = Decimal("1.1") * Decimal("1.1") - 1
        assert perf.cumulative_return == expected

    def test_loss_then_gain(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("-0.10"))
        perf.record_return(Decimal("0.10"))
        expected = Decimal("0.9") * Decimal("1.1") - 1
        assert perf.cumulative_return == expected

    def test_empty_returns_zero(self, perf: StrategyPerformance) -> None:
        assert perf.cumulative_return == Decimal("0")


class TestAvgReturn:
    def test_average(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.10"))
        perf.record_return(Decimal("0.20"))
        assert perf.avg_return == Decimal("0.15")

    def test_empty(self, perf: StrategyPerformance) -> None:
        assert perf.avg_return == Decimal("0")


class TestSharpeRatio:
    def test_positive_sharpe(self, perf: StrategyPerformance) -> None:
        for _ in range(10):
            perf.record_return(Decimal("0.02"))
        assert perf.sharpe_ratio > Decimal("0")

    def test_insufficient_data(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.05"))
        assert perf.sharpe_ratio == Decimal("0")

    def test_zero_std_returns_zero(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.05"))
        perf.record_return(Decimal("0.05"))
        assert perf.sharpe_ratio == Decimal("0")


class TestMaxDrawdown:
    def test_drawdown_from_peak(self, perf: StrategyPerformance) -> None:
        perf.record_equity(Decimal("10000"))
        perf.record_equity(Decimal("11000"))
        perf.record_equity(Decimal("9900"))
        perf.record_equity(Decimal("10500"))
        assert perf.max_drawdown == Decimal("0.1")

    def test_no_drawdown(self, perf: StrategyPerformance) -> None:
        perf.record_equity(Decimal("10000"))
        perf.record_equity(Decimal("11000"))
        perf.record_equity(Decimal("12000"))
        assert perf.max_drawdown == Decimal("0")

    def test_empty(self, perf: StrategyPerformance) -> None:
        assert perf.max_drawdown == Decimal("0")


class TestRecentReturns:
    def test_returns_last_20(self, perf: StrategyPerformance) -> None:
        for i in range(30):
            perf.record_return(Decimal(str(i)))
        recent = perf.recent_returns
        assert len(recent) == 20
        assert recent[0] == Decimal("10")

    def test_returns_all_if_less_than_20(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.05"))
        perf.record_return(Decimal("0.10"))
        assert len(perf.recent_returns) == 2


class TestReset:
    def test_clears_everything(self, perf: StrategyPerformance) -> None:
        perf.record_return(Decimal("0.05"))
        perf.record_equity(Decimal("10000"))
        perf.reset()
        assert perf.total_trades == 0
        assert perf.cumulative_return == Decimal("0")
        assert perf.max_drawdown == Decimal("0")
