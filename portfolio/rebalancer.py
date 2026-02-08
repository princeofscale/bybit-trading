from decimal import Decimal

import structlog

from portfolio.allocation import AllocationResult

logger = structlog.get_logger("rebalancer")


class RebalanceAction:
    def __init__(
        self,
        strategy_name: str,
        current_pct: Decimal,
        target_pct: Decimal,
        delta_pct: Decimal,
        delta_usd: Decimal,
    ) -> None:
        self.strategy_name = strategy_name
        self.current_pct = current_pct
        self.target_pct = target_pct
        self.delta_pct = delta_pct
        self.delta_usd = delta_usd

    @property
    def needs_increase(self) -> bool:
        return self.delta_usd > 0

    @property
    def needs_decrease(self) -> bool:
        return self.delta_usd < 0


class Rebalancer:
    def __init__(
        self,
        threshold_pct: Decimal = Decimal("0.05"),
        max_turnover_pct: Decimal = Decimal("0.20"),
    ) -> None:
        self._threshold = threshold_pct
        self._max_turnover = max_turnover_pct

    def calculate_rebalance(
        self,
        current_allocations: dict[str, Decimal],
        target: AllocationResult,
        total_equity: Decimal,
    ) -> list[RebalanceAction]:
        actions: list[RebalanceAction] = []
        all_strategies = set(current_allocations.keys()) | set(target.allocations.keys())

        for name in all_strategies:
            current_pct = current_allocations.get(name, Decimal("0"))
            target_pct = target.get(name)
            delta_pct = target_pct - current_pct

            if abs(delta_pct) < self._threshold:
                continue

            delta_usd = delta_pct * total_equity
            actions.append(RebalanceAction(
                strategy_name=name,
                current_pct=current_pct,
                target_pct=target_pct,
                delta_pct=delta_pct,
                delta_usd=delta_usd,
            ))

        return self._cap_turnover(actions, total_equity)

    def needs_rebalance(
        self,
        current: dict[str, Decimal],
        target: AllocationResult,
    ) -> bool:
        all_strategies = set(current.keys()) | set(target.allocations.keys())
        for name in all_strategies:
            cur = current.get(name, Decimal("0"))
            tgt = target.get(name)
            if abs(tgt - cur) >= self._threshold:
                return True
        return False

    def _cap_turnover(
        self,
        actions: list[RebalanceAction],
        total_equity: Decimal,
    ) -> list[RebalanceAction]:
        total_turnover = sum(abs(a.delta_usd) for a in actions)
        max_usd = self._max_turnover * total_equity

        if total_turnover <= max_usd or total_turnover == 0:
            return actions

        scale = max_usd / total_turnover
        capped: list[RebalanceAction] = []
        for a in actions:
            new_delta_usd = a.delta_usd * scale
            new_delta_pct = new_delta_usd / total_equity if total_equity > 0 else Decimal("0")
            capped.append(RebalanceAction(
                strategy_name=a.strategy_name,
                current_pct=a.current_pct,
                target_pct=a.current_pct + new_delta_pct,
                delta_pct=new_delta_pct,
                delta_usd=new_delta_usd,
            ))
        return capped
