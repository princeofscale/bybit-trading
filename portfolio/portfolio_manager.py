from decimal import Decimal

import structlog

from portfolio.allocation import AllocationEngine, AllocationResult
from portfolio.performance import StrategyPerformance
from portfolio.rebalancer import Rebalancer, RebalanceAction

logger = structlog.get_logger("portfolio_manager")


class PortfolioManager:
    def __init__(
        self,
        strategy_names: list[str],
        total_equity: Decimal,
        rebalance_threshold: Decimal = Decimal("0.05"),
        max_turnover: Decimal = Decimal("0.20"),
        min_allocation: Decimal = Decimal("0.05"),
    ) -> None:
        self._strategy_names = strategy_names
        self._total_equity = total_equity
        self._allocator = AllocationEngine(min_allocation)
        self._rebalancer = Rebalancer(rebalance_threshold, max_turnover)
        self._performances: dict[str, StrategyPerformance] = {
            name: StrategyPerformance(name) for name in strategy_names
        }
        self._current_allocations: dict[str, Decimal] = {}
        self._target: AllocationResult | None = None
        self._initialize_equal()

    def _initialize_equal(self) -> None:
        target = self._allocator.equal_weight(self._strategy_names)
        self._current_allocations = dict(target.allocations)
        self._target = target

    @property
    def strategy_names(self) -> list[str]:
        return self._strategy_names

    @property
    def total_equity(self) -> Decimal:
        return self._total_equity

    @property
    def current_allocations(self) -> dict[str, Decimal]:
        return dict(self._current_allocations)

    @property
    def performances(self) -> dict[str, StrategyPerformance]:
        return self._performances

    def update_equity(self, equity: Decimal) -> None:
        self._total_equity = equity

    def record_trade(self, strategy_name: str, pnl_pct: Decimal) -> None:
        if strategy_name in self._performances:
            self._performances[strategy_name].record_return(pnl_pct)

    def record_equity_snapshot(self, strategy_name: str, equity: Decimal) -> None:
        if strategy_name in self._performances:
            self._performances[strategy_name].record_equity(equity)

    def get_strategy_budget(self, strategy_name: str) -> Decimal:
        alloc = self._current_allocations.get(strategy_name, Decimal("0"))
        return self._total_equity * alloc

    def calculate_target_allocation(self, method: str = "performance") -> AllocationResult:
        if method == "equal":
            target = self._allocator.equal_weight(self._strategy_names)
        elif method == "performance":
            target = self._allocator.performance_weighted(self._performances)
        elif method == "risk_parity":
            target = self._allocator.risk_parity(self._performances)
        else:
            target = self._allocator.equal_weight(self._strategy_names)
        self._target = target
        return target

    def check_rebalance_needed(self) -> bool:
        if self._target is None:
            return False
        return self._rebalancer.needs_rebalance(
            self._current_allocations, self._target,
        )

    def execute_rebalance(self) -> list[RebalanceAction]:
        if self._target is None:
            self.calculate_target_allocation()

        actions = self._rebalancer.calculate_rebalance(
            self._current_allocations, self._target, self._total_equity,
        )

        for action in actions:
            new_alloc = self._current_allocations.get(action.strategy_name, Decimal("0"))
            new_alloc += action.delta_pct
            self._current_allocations[action.strategy_name] = max(new_alloc, Decimal("0"))

        return actions

    def get_performance_summary(self) -> dict[str, dict[str, Decimal]]:
        summary: dict[str, dict[str, Decimal]] = {}
        for name, perf in self._performances.items():
            summary[name] = {
                "win_rate": perf.win_rate,
                "cumulative_return": perf.cumulative_return,
                "sharpe": perf.sharpe_ratio,
                "max_drawdown": perf.max_drawdown,
                "total_trades": Decimal(str(perf.total_trades)),
            }
        return summary

    def add_strategy(self, name: str) -> None:
        if name not in self._strategy_names:
            self._strategy_names.append(name)
            self._performances[name] = StrategyPerformance(name)
            self._current_allocations[name] = Decimal("0")

    def remove_strategy(self, name: str) -> None:
        if name in self._strategy_names:
            self._strategy_names.remove(name)
            self._performances.pop(name, None)
            freed = self._current_allocations.pop(name, Decimal("0"))
            remaining = [n for n in self._strategy_names]
            if remaining:
                share = freed / Decimal(str(len(remaining)))
                for r in remaining:
                    self._current_allocations[r] = self._current_allocations.get(r, Decimal("0")) + share
