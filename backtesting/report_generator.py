import math
from decimal import Decimal

from backtesting.models import BacktestResult, BacktestTrade, PerformanceMetrics


BARS_PER_YEAR_15M = 365 * 24 * 4


class ReportGenerator:
    def __init__(self, annualization_factor: int = BARS_PER_YEAR_15M) -> None:
        self._ann_factor = annualization_factor

    def calculate_metrics(self, result: BacktestResult) -> PerformanceMetrics:
        trades = result.trades
        if not trades:
            return PerformanceMetrics()

        initial = result.config.initial_equity
        final = result.final_equity
        total_return = (final - initial) / initial if initial > 0 else Decimal("0")

        winners = [t for t in trades if t.pnl > 0]
        losers = [t for t in trades if t.pnl <= 0]

        win_rate = Decimal(str(len(winners))) / Decimal(str(len(trades))) if trades else Decimal("0")

        avg_win = (
            sum(t.pnl for t in winners) / Decimal(str(len(winners)))
            if winners else Decimal("0")
        )
        avg_loss = (
            sum(abs(t.pnl) for t in losers) / Decimal(str(len(losers)))
            if losers else Decimal("0")
        )

        gross_profit = sum(t.pnl for t in winners)
        gross_loss = sum(abs(t.pnl) for t in losers)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else Decimal("0")

        avg_wl_ratio = avg_win / avg_loss if avg_loss > 0 else Decimal("0")

        max_dd, max_dd_duration = self._max_drawdown(result)

        returns = self._bar_returns(result)
        sharpe = self._sharpe_ratio(returns)
        sortino = self._sortino_ratio(returns)
        calmar = self._calmar_ratio(total_return, max_dd, result)

        ann_return = self._annualized_return(total_return, result)

        total_bars = sum(t.bars_held for t in trades)
        avg_bars = Decimal(str(total_bars)) / Decimal(str(len(trades))) if trades else Decimal("0")

        total_comm = sum(t.commission for t in trades)
        total_slip = sum(t.slippage for t in trades)

        expectancy = sum(t.pnl for t in trades) / Decimal(str(len(trades))) if trades else Decimal("0")

        kelly = self._kelly_pct(win_rate, avg_wl_ratio)

        return PerformanceMetrics(
            total_return_pct=total_return,
            annualized_return_pct=ann_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd,
            max_drawdown_duration_bars=max_dd_duration,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_win_loss_ratio=avg_wl_ratio,
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            avg_bars_held=avg_bars,
            total_commission=total_comm,
            total_slippage=total_slip,
            expectancy=expectancy,
            kelly_pct=kelly,
        )

    def _max_drawdown(self, result: BacktestResult) -> tuple[Decimal, int]:
        if not result.equity_curve:
            return Decimal("0"), 0

        peak = result.config.initial_equity
        max_dd = Decimal("0")
        dd_start = 0
        max_dd_dur = 0
        cur_dur = 0

        for point in result.equity_curve:
            if point.equity > peak:
                peak = point.equity
                cur_dur = 0
            else:
                cur_dur += 1

            dd = (peak - point.equity) / peak if peak > 0 else Decimal("0")
            if dd > max_dd:
                max_dd = dd
                max_dd_dur = cur_dur

        return max_dd, max_dd_dur

    def _bar_returns(self, result: BacktestResult) -> list[Decimal]:
        curve = result.equity_curve
        if len(curve) < 2:
            return []
        returns = []
        for i in range(1, len(curve)):
            prev = curve[i - 1].equity
            if prev > 0:
                returns.append((curve[i].equity - prev) / prev)
            else:
                returns.append(Decimal("0"))
        return returns

    def _sharpe_ratio(self, returns: list[Decimal]) -> Decimal:
        if len(returns) < 2:
            return Decimal("0")
        mean_r = sum(returns) / Decimal(str(len(returns)))
        variance = sum((r - mean_r) ** 2 for r in returns) / Decimal(str(len(returns)))
        std = Decimal(str(math.sqrt(float(variance)))) if variance > 0 else Decimal("0")
        if std == 0:
            return Decimal("0")
        ann_factor = Decimal(str(math.sqrt(self._ann_factor)))
        return (mean_r / std) * ann_factor

    def _sortino_ratio(self, returns: list[Decimal]) -> Decimal:
        if len(returns) < 2:
            return Decimal("0")
        mean_r = sum(returns) / Decimal(str(len(returns)))
        downside = [r for r in returns if r < 0]
        if not downside:
            return Decimal("0") if mean_r <= 0 else Decimal("99.99")
        down_var = sum(r ** 2 for r in downside) / Decimal(str(len(returns)))
        down_std = Decimal(str(math.sqrt(float(down_var)))) if down_var > 0 else Decimal("0")
        if down_std == 0:
            return Decimal("0")
        ann_factor = Decimal(str(math.sqrt(self._ann_factor)))
        return (mean_r / down_std) * ann_factor

    def _calmar_ratio(
        self, total_return: Decimal, max_dd: Decimal, result: BacktestResult,
    ) -> Decimal:
        if max_dd <= 0:
            return Decimal("0")
        ann_return = self._annualized_return(total_return, result)
        return ann_return / max_dd

    def _annualized_return(self, total_return: Decimal, result: BacktestResult) -> Decimal:
        n_bars = len(result.equity_curve)
        if n_bars <= 0:
            return Decimal("0")
        years = Decimal(str(n_bars)) / Decimal(str(self._ann_factor))
        if years <= 0:
            return Decimal("0")
        try:
            ann = (1 + float(total_return)) ** (1 / float(years)) - 1
            return Decimal(str(ann))
        except (OverflowError, ValueError, ZeroDivisionError):
            return Decimal("0")

    def _kelly_pct(self, win_rate: Decimal, avg_wl_ratio: Decimal) -> Decimal:
        if avg_wl_ratio <= 0:
            return Decimal("0")
        kelly = win_rate - (1 - win_rate) / avg_wl_ratio
        return max(Decimal("0"), kelly)
