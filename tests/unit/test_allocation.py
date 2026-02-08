from decimal import Decimal

import pytest

from portfolio.allocation import AllocationEngine, AllocationResult
from portfolio.performance import StrategyPerformance


@pytest.fixture
def engine() -> AllocationEngine:
    return AllocationEngine(min_allocation=Decimal("0.05"))


def _make_perf(name: str, returns: list[str]) -> StrategyPerformance:
    p = StrategyPerformance(name)
    for r in returns:
        p.record_return(Decimal(r))
    return p


class TestAllocationResult:
    def test_get_existing(self) -> None:
        ar = AllocationResult({"a": Decimal("0.5"), "b": Decimal("0.5")})
        assert ar.get("a") == Decimal("0.5")

    def test_get_missing(self) -> None:
        ar = AllocationResult({"a": Decimal("1")})
        assert ar.get("b") == Decimal("0")

    def test_total(self) -> None:
        ar = AllocationResult({"a": Decimal("0.3"), "b": Decimal("0.7")})
        assert ar.total == Decimal("1.0")


class TestEqualWeight:
    def test_two_strategies(self, engine: AllocationEngine) -> None:
        result = engine.equal_weight(["a", "b"])
        assert result.get("a") == Decimal("0.5")
        assert result.get("b") == Decimal("0.5")

    def test_three_strategies(self, engine: AllocationEngine) -> None:
        result = engine.equal_weight(["a", "b", "c"])
        expected = Decimal("1") / Decimal("3")
        assert result.get("a") == expected

    def test_empty(self, engine: AllocationEngine) -> None:
        result = engine.equal_weight([])
        assert result.total == Decimal("0")

    def test_single_strategy(self, engine: AllocationEngine) -> None:
        result = engine.equal_weight(["only"])
        assert result.get("only") == Decimal("1")


class TestPerformanceWeighted:
    def test_better_performance_gets_more(self, engine: AllocationEngine) -> None:
        perfs = {
            "good": _make_perf("good", ["0.05", "0.04", "0.06", "0.03", "0.05"]),
            "bad": _make_perf("bad", ["-0.02", "0.01", "-0.03", "0.00", "-0.01"]),
        }
        result = engine.performance_weighted(perfs)
        assert result.get("good") > result.get("bad")

    def test_all_negative_falls_back_equal(self, engine: AllocationEngine) -> None:
        perfs = {
            "a": _make_perf("a", ["-0.05", "-0.03"]),
            "b": _make_perf("b", ["-0.02", "-0.04"]),
        }
        result = engine.performance_weighted(perfs)
        assert result.get("a") == Decimal("0.5")

    def test_sums_to_one(self, engine: AllocationEngine) -> None:
        perfs = {
            "a": _make_perf("a", ["0.05", "0.03", "0.04"]),
            "b": _make_perf("b", ["0.02", "0.01", "0.03"]),
            "c": _make_perf("c", ["0.01", "0.02", "0.01"]),
        }
        result = engine.performance_weighted(perfs)
        assert abs(result.total - Decimal("1")) < Decimal("0.001")

    def test_empty(self, engine: AllocationEngine) -> None:
        result = engine.performance_weighted({})
        assert result.total == Decimal("0")


class TestRiskParity:
    def test_lower_risk_gets_more(self, engine: AllocationEngine) -> None:
        low_risk = StrategyPerformance("low")
        low_risk.record_equity(Decimal("10000"))
        low_risk.record_equity(Decimal("9900"))
        low_risk.record_equity(Decimal("10100"))

        high_risk = StrategyPerformance("high")
        high_risk.record_equity(Decimal("10000"))
        high_risk.record_equity(Decimal("8000"))
        high_risk.record_equity(Decimal("9500"))

        result = engine.risk_parity({"low": low_risk, "high": high_risk})
        assert result.get("low") > result.get("high")

    def test_sums_to_one(self, engine: AllocationEngine) -> None:
        p1 = StrategyPerformance("a")
        p1.record_equity(Decimal("10000"))
        p1.record_equity(Decimal("9500"))
        p2 = StrategyPerformance("b")
        p2.record_equity(Decimal("10000"))
        p2.record_equity(Decimal("9000"))
        result = engine.risk_parity({"a": p1, "b": p2})
        assert abs(result.total - Decimal("1")) < Decimal("0.001")


class TestMinAllocation:
    def test_enforces_minimum(self) -> None:
        engine = AllocationEngine(min_allocation=Decimal("0.10"))
        perfs = {
            "dominant": _make_perf("dominant", ["0.10", "0.08", "0.09", "0.07", "0.10"]),
            "weak": _make_perf("weak", ["0.001", "0.001", "0.001", "0.001", "0.001"]),
        }
        result = engine.performance_weighted(perfs)
        assert result.get("weak") >= Decimal("0.09")
