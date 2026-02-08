from decimal import Decimal

import pytest

from portfolio.portfolio_manager import PortfolioManager


@pytest.fixture
def pm() -> PortfolioManager:
    return PortfolioManager(
        strategy_names=["trend", "mean_rev", "momentum"],
        total_equity=Decimal("30000"),
        rebalance_threshold=Decimal("0.05"),
        max_turnover=Decimal("0.20"),
    )


class TestInit:
    def test_equal_allocation(self, pm: PortfolioManager) -> None:
        allocs = pm.current_allocations
        expected = Decimal("1") / Decimal("3")
        for name in ["trend", "mean_rev", "momentum"]:
            assert allocs[name] == expected

    def test_strategy_names(self, pm: PortfolioManager) -> None:
        assert pm.strategy_names == ["trend", "mean_rev", "momentum"]

    def test_equity(self, pm: PortfolioManager) -> None:
        assert pm.total_equity == Decimal("30000")


class TestGetBudget:
    def test_equal_budget(self, pm: PortfolioManager) -> None:
        budget = pm.get_strategy_budget("trend")
        expected = Decimal("30000") / Decimal("3")
        assert abs(budget - expected) < Decimal("0.01")

    def test_unknown_strategy_zero(self, pm: PortfolioManager) -> None:
        assert pm.get_strategy_budget("nonexistent") == Decimal("0")


class TestRecordTrade:
    def test_records_in_performance(self, pm: PortfolioManager) -> None:
        pm.record_trade("trend", Decimal("0.05"))
        pm.record_trade("trend", Decimal("-0.02"))
        perf = pm.performances["trend"]
        assert perf.total_trades == 2
        assert perf.win_rate == Decimal("0.5")

    def test_ignores_unknown_strategy(self, pm: PortfolioManager) -> None:
        pm.record_trade("unknown", Decimal("0.05"))


class TestUpdateEquity:
    def test_updates_total(self, pm: PortfolioManager) -> None:
        pm.update_equity(Decimal("35000"))
        assert pm.total_equity == Decimal("35000")

    def test_budget_reflects_new_equity(self, pm: PortfolioManager) -> None:
        pm.update_equity(Decimal("60000"))
        budget = pm.get_strategy_budget("trend")
        assert budget == Decimal("60000") / Decimal("3")


class TestCalculateTargetAllocation:
    def test_equal_method(self, pm: PortfolioManager) -> None:
        target = pm.calculate_target_allocation("equal")
        expected = Decimal("1") / Decimal("3")
        assert target.get("trend") == expected

    def test_performance_method(self, pm: PortfolioManager) -> None:
        returns_trend = ["0.05", "0.03", "0.06", "0.04", "0.07"]
        returns_mean = ["0.01", "0.02", "-0.01", "0.03", "0.00"]
        returns_mom = ["-0.02", "-0.01", "-0.03", "0.01", "-0.02"]
        for i in range(5):
            pm.record_trade("trend", Decimal(returns_trend[i]))
            pm.record_trade("mean_rev", Decimal(returns_mean[i]))
            pm.record_trade("momentum", Decimal(returns_mom[i]))
        target = pm.calculate_target_allocation("performance")
        assert target.get("trend") > target.get("momentum")

    def test_risk_parity_method(self, pm: PortfolioManager) -> None:
        pm.record_equity_snapshot("trend", Decimal("10000"))
        pm.record_equity_snapshot("trend", Decimal("9500"))
        pm.record_equity_snapshot("mean_rev", Decimal("10000"))
        pm.record_equity_snapshot("mean_rev", Decimal("8000"))
        pm.record_equity_snapshot("momentum", Decimal("10000"))
        pm.record_equity_snapshot("momentum", Decimal("9000"))
        target = pm.calculate_target_allocation("risk_parity")
        assert target.get("trend") > target.get("mean_rev")


class TestRebalance:
    def test_no_rebalance_when_balanced(self, pm: PortfolioManager) -> None:
        pm.calculate_target_allocation("equal")
        assert pm.check_rebalance_needed() is False

    def test_rebalance_after_drift(self, pm: PortfolioManager) -> None:
        for _ in range(10):
            pm.record_trade("trend", Decimal("0.05"))
            pm.record_trade("mean_rev", Decimal("-0.02"))
            pm.record_trade("momentum", Decimal("0.01"))
        pm.calculate_target_allocation("performance")
        actions = pm.execute_rebalance()
        assert isinstance(actions, list)

    def test_execute_rebalance_updates_allocations(self, pm: PortfolioManager) -> None:
        for _ in range(10):
            pm.record_trade("trend", Decimal("0.06"))
            pm.record_trade("mean_rev", Decimal("-0.03"))
            pm.record_trade("momentum", Decimal("0.01"))
        pm.calculate_target_allocation("performance")
        pm.execute_rebalance()
        allocs = pm.current_allocations
        total = sum(allocs.values())
        assert total > Decimal("0")


class TestPerformanceSummary:
    def test_summary_structure(self, pm: PortfolioManager) -> None:
        pm.record_trade("trend", Decimal("0.05"))
        summary = pm.get_performance_summary()
        assert "trend" in summary
        assert "win_rate" in summary["trend"]
        assert "sharpe" in summary["trend"]
        assert "max_drawdown" in summary["trend"]
        assert summary["trend"]["total_trades"] == Decimal("1")


class TestAddRemoveStrategy:
    def test_add_strategy(self, pm: PortfolioManager) -> None:
        pm.add_strategy("grid")
        assert "grid" in pm.strategy_names
        assert pm.get_strategy_budget("grid") == Decimal("0")

    def test_add_duplicate_ignored(self, pm: PortfolioManager) -> None:
        pm.add_strategy("trend")
        assert pm.strategy_names.count("trend") == 1

    def test_remove_strategy(self, pm: PortfolioManager) -> None:
        pm.remove_strategy("momentum")
        assert "momentum" not in pm.strategy_names
        assert len(pm.strategy_names) == 2
        allocs = pm.current_allocations
        assert "momentum" not in allocs

    def test_remove_redistributes(self, pm: PortfolioManager) -> None:
        pm.remove_strategy("momentum")
        allocs = pm.current_allocations
        total = sum(allocs.values())
        assert abs(total - Decimal("1")) < Decimal("0.001")
