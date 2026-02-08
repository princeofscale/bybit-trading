from decimal import Decimal

import pytest

from portfolio.allocation import AllocationResult
from portfolio.rebalancer import RebalanceAction, Rebalancer


@pytest.fixture
def rebalancer() -> Rebalancer:
    return Rebalancer(
        threshold_pct=Decimal("0.05"),
        max_turnover_pct=Decimal("0.20"),
    )


class TestNeedsRebalance:
    def test_needs_when_drift_exceeds_threshold(self, rebalancer: Rebalancer) -> None:
        current = {"a": Decimal("0.6"), "b": Decimal("0.4")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        assert rebalancer.needs_rebalance(current, target) is True

    def test_no_need_when_within_threshold(self, rebalancer: Rebalancer) -> None:
        current = {"a": Decimal("0.52"), "b": Decimal("0.48")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        assert rebalancer.needs_rebalance(current, target) is False

    def test_new_strategy_added(self, rebalancer: Rebalancer) -> None:
        current = {"a": Decimal("1.0")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        assert rebalancer.needs_rebalance(current, target) is True


class TestCalculateRebalance:
    def test_generates_actions(self, rebalancer: Rebalancer) -> None:
        current = {"a": Decimal("0.7"), "b": Decimal("0.3")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        actions = rebalancer.calculate_rebalance(current, target, Decimal("10000"))
        assert len(actions) == 2

        a_action = next(a for a in actions if a.strategy_name == "a")
        b_action = next(a for a in actions if a.strategy_name == "b")
        assert a_action.needs_decrease is True
        assert b_action.needs_increase is True

    def test_skips_within_threshold(self, rebalancer: Rebalancer) -> None:
        current = {"a": Decimal("0.52"), "b": Decimal("0.48")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        actions = rebalancer.calculate_rebalance(current, target, Decimal("10000"))
        assert len(actions) == 0

    def test_delta_usd_correct(self) -> None:
        reb = Rebalancer(threshold_pct=Decimal("0.05"), max_turnover_pct=Decimal("1.0"))
        current = {"a": Decimal("0.7"), "b": Decimal("0.3")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        actions = reb.calculate_rebalance(current, target, Decimal("10000"))
        a_action = next(a for a in actions if a.strategy_name == "a")
        assert a_action.delta_usd == Decimal("-2000")

    def test_new_strategy_gets_allocation(self) -> None:
        reb = Rebalancer(threshold_pct=Decimal("0.05"), max_turnover_pct=Decimal("1.0"))
        current = {"a": Decimal("1.0")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        actions = reb.calculate_rebalance(current, target, Decimal("10000"))
        b_action = next(a for a in actions if a.strategy_name == "b")
        assert b_action.needs_increase is True
        assert b_action.delta_usd == Decimal("5000")


class TestTurnoverCap:
    def test_caps_large_rebalance(self) -> None:
        reb = Rebalancer(
            threshold_pct=Decimal("0.01"),
            max_turnover_pct=Decimal("0.10"),
        )
        current = {"a": Decimal("0.8"), "b": Decimal("0.2")}
        target = AllocationResult({"a": Decimal("0.2"), "b": Decimal("0.8")})
        actions = reb.calculate_rebalance(current, target, Decimal("10000"))

        total_turnover = sum(abs(a.delta_usd) for a in actions)
        assert total_turnover <= Decimal("1000") + Decimal("1")

    def test_small_rebalance_not_capped(self, rebalancer: Rebalancer) -> None:
        current = {"a": Decimal("0.55"), "b": Decimal("0.45")}
        target = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        actions = rebalancer.calculate_rebalance(current, target, Decimal("10000"))
        if actions:
            a_action = next(a for a in actions if a.strategy_name == "a")
            assert a_action.delta_usd == Decimal("-500")


class TestRebalanceAction:
    def test_increase_flag(self) -> None:
        a = RebalanceAction("x", Decimal("0.3"), Decimal("0.5"), Decimal("0.2"), Decimal("2000"))
        assert a.needs_increase is True
        assert a.needs_decrease is False

    def test_decrease_flag(self) -> None:
        a = RebalanceAction("x", Decimal("0.5"), Decimal("0.3"), Decimal("-0.2"), Decimal("-2000"))
        assert a.needs_increase is False
        assert a.needs_decrease is True
