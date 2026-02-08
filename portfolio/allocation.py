from decimal import Decimal

from portfolio.performance import StrategyPerformance


class AllocationResult:
    def __init__(self, allocations: dict[str, Decimal]) -> None:
        self.allocations = allocations

    def get(self, strategy_name: str) -> Decimal:
        return self.allocations.get(strategy_name, Decimal("0"))

    @property
    def total(self) -> Decimal:
        return sum(self.allocations.values())


class AllocationEngine:
    def __init__(self, min_allocation: Decimal = Decimal("0.05")) -> None:
        self._min_alloc = min_allocation

    def equal_weight(self, strategy_names: list[str]) -> AllocationResult:
        if not strategy_names:
            return AllocationResult({})
        weight = Decimal("1") / Decimal(str(len(strategy_names)))
        return AllocationResult({s: weight for s in strategy_names})

    def performance_weighted(
        self,
        performances: dict[str, StrategyPerformance],
    ) -> AllocationResult:
        if not performances:
            return AllocationResult({})

        scores: dict[str, Decimal] = {}
        for name, perf in performances.items():
            sharpe = perf.recent_sharpe
            score = max(sharpe, Decimal("0"))
            scores[name] = score

        total_score = sum(scores.values())
        if total_score <= 0:
            return self.equal_weight(list(performances.keys()))

        raw: dict[str, Decimal] = {}
        for name, score in scores.items():
            raw[name] = score / total_score

        return self._apply_min_allocation(raw)

    def risk_parity(
        self,
        performances: dict[str, StrategyPerformance],
    ) -> AllocationResult:
        if not performances:
            return AllocationResult({})

        inv_vol: dict[str, Decimal] = {}
        for name, perf in performances.items():
            dd = perf.max_drawdown
            vol_proxy = dd if dd > 0 else Decimal("0.01")
            inv_vol[name] = Decimal("1") / vol_proxy

        total = sum(inv_vol.values())
        if total <= 0:
            return self.equal_weight(list(performances.keys()))

        raw = {name: iv / total for name, iv in inv_vol.items()}
        return self._apply_min_allocation(raw)

    def _apply_min_allocation(self, raw: dict[str, Decimal]) -> AllocationResult:
        adjusted: dict[str, Decimal] = {}
        for name, weight in raw.items():
            adjusted[name] = max(weight, self._min_alloc)

        total = sum(adjusted.values())
        if total > 0:
            adjusted = {n: w / total for n, w in adjusted.items()}

        return AllocationResult(adjusted)
