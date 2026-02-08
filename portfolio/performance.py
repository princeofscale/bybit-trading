import math
from decimal import Decimal


class StrategyPerformance:
    def __init__(self, strategy_name: str) -> None:
        self.strategy_name = strategy_name
        self._returns: list[Decimal] = []
        self._equity_curve: list[Decimal] = []
        self._trade_count = 0
        self._win_count = 0

    def record_return(self, pnl_pct: Decimal) -> None:
        self._returns.append(pnl_pct)
        self._trade_count += 1
        if pnl_pct > 0:
            self._win_count += 1

    def record_equity(self, equity: Decimal) -> None:
        self._equity_curve.append(equity)

    @property
    def total_trades(self) -> int:
        return self._trade_count

    @property
    def win_rate(self) -> Decimal:
        if self._trade_count == 0:
            return Decimal("0")
        return Decimal(str(self._win_count)) / Decimal(str(self._trade_count))

    @property
    def cumulative_return(self) -> Decimal:
        if not self._returns:
            return Decimal("0")
        product = Decimal("1")
        for r in self._returns:
            product *= (1 + r)
        return product - 1

    @property
    def avg_return(self) -> Decimal:
        if not self._returns:
            return Decimal("0")
        return sum(self._returns) / Decimal(str(len(self._returns)))

    @property
    def sharpe_ratio(self) -> Decimal:
        if len(self._returns) < 2:
            return Decimal("0")
        returns_f = [float(r) for r in self._returns]
        mean = sum(returns_f) / len(returns_f)
        var = sum((r - mean) ** 2 for r in returns_f) / len(returns_f)
        std = math.sqrt(var) if var > 0 else 0
        if std == 0:
            return Decimal("0")
        return Decimal(str(mean / std))

    @property
    def max_drawdown(self) -> Decimal:
        if not self._equity_curve:
            return Decimal("0")
        peak = self._equity_curve[0]
        max_dd = Decimal("0")
        for eq in self._equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else Decimal("0")
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def recent_returns(self) -> list[Decimal]:
        return self._returns[-20:] if self._returns else []

    @property
    def recent_sharpe(self) -> Decimal:
        recent = self.recent_returns
        if len(recent) < 2:
            return Decimal("0")
        rf = [float(r) for r in recent]
        mean = sum(rf) / len(rf)
        var = sum((r - mean) ** 2 for r in rf) / len(rf)
        std = math.sqrt(var) if var > 0 else 0
        if std == 0:
            return Decimal("0")
        return Decimal(str(mean / std))

    def reset(self) -> None:
        self._returns.clear()
        self._equity_curve.clear()
        self._trade_count = 0
        self._win_count = 0
