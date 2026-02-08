from decimal import Decimal
from pathlib import Path

import structlog

from journal.reader import JournalReader
from journal.models import TradeRecord, SignalRecord, OrderRecord, EquitySnapshotRecord, RiskEventRecord

logger = structlog.get_logger("session_report")


class SessionReport:
    def __init__(self, journal_path: Path) -> None:
        self._reader = JournalReader(journal_path)

    async def initialize(self) -> None:
        await self._reader.initialize()

    async def close(self) -> None:
        await self._reader.close()

    async def generate(self, session_id: str) -> dict[str, dict[str, float | int | str]]:
        trades = await self._reader.get_trades(session_id, limit=10000)
        signals = await self._reader.get_signals(session_id, limit=10000)
        orders = await self._reader.get_orders(session_id, limit=10000)
        risk_events = await self._reader.get_risk_events(session_id, limit=1000)
        snapshots = await self._reader.get_equity_snapshots(session_id, limit=10000)

        report = {
            "trade_stats": self._trade_stats(trades),
            "risk_summary": self._risk_summary(risk_events, signals),
            "execution_quality": self._execution_quality(orders),
            "equity_curve": self._equity_curve(snapshots),
            "per_strategy": self._per_strategy(trades, signals),
        }

        return report

    def _trade_stats(self, trades: list[TradeRecord]) -> dict[str, float | int]:
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "sharpe": 0.0,
                "total_pnl": 0.0,
            }

        wins = [t for t in trades if t.realized_pnl > 0]
        losses = [t for t in trades if t.realized_pnl < 0]

        win_rate = len(wins) / len(trades) if trades else 0.0

        gross_wins = sum(t.realized_pnl for t in wins)
        gross_losses = abs(sum(t.realized_pnl for t in losses))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0.0

        avg_win = gross_wins / len(wins) if wins else 0.0
        avg_loss = gross_losses / len(losses) if losses else 0.0

        returns = [t.pnl_pct for t in trades]
        mean_return = sum(returns) / len(returns) if returns else 0.0
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns) if len(returns) > 1 else 0.0
        std_dev = variance ** 0.5
        sharpe = (mean_return / std_dev) if std_dev > 0 else 0.0

        total_pnl = sum(t.realized_pnl for t in trades)

        return {
            "total_trades": len(trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "sharpe": sharpe,
            "total_pnl": total_pnl,
        }

    def _risk_summary(
        self,
        risk_events: list[RiskEventRecord],
        signals: list[SignalRecord],
    ) -> dict[str, float | int]:
        total_signals = len(signals)
        approved = len([s for s in signals if s.approved])
        rejected = total_signals - approved
        rejection_rate = rejected / total_signals if total_signals > 0 else 0.0

        events_by_type: dict[str, int] = {}
        for event in risk_events:
            events_by_type[event.event_type] = events_by_type.get(event.event_type, 0) + 1

        return {
            "total_signals": total_signals,
            "approved_signals": approved,
            "rejected_signals": rejected,
            "rejection_rate": rejection_rate,
            "risk_events": len(risk_events),
            **{f"{k}_events": v for k, v in events_by_type.items()},
        }

    def _execution_quality(self, orders: list[OrderRecord]) -> dict[str, float | int]:
        if not orders:
            return {
                "total_orders": 0,
                "filled_orders": 0,
                "fill_rate": 0.0,
                "avg_slippage": 0.0,
                "total_fees": 0.0,
            }

        filled = [o for o in orders if o.status == "Filled"]
        fill_rate = len(filled) / len(orders) if orders else 0.0

        slippages = []
        for order in filled:
            if order.price and order.avg_fill_price:
                slippage_pct = abs(order.avg_fill_price - order.price) / order.price
                slippages.append(slippage_pct)

        avg_slippage = sum(slippages) / len(slippages) if slippages else 0.0
        total_fees = sum(o.fee for o in orders)

        return {
            "total_orders": len(orders),
            "filled_orders": len(filled),
            "fill_rate": fill_rate,
            "avg_slippage": avg_slippage,
            "total_fees": total_fees,
        }

    def _equity_curve(self, snapshots: list[EquitySnapshotRecord]) -> dict[str, float | int]:
        if not snapshots:
            return {
                "start_equity": 0.0,
                "end_equity": 0.0,
                "max_drawdown": 0.0,
                "return_pct": 0.0,
                "snapshots_count": 0,
            }

        start_equity = snapshots[0].total_equity
        end_equity = snapshots[-1].total_equity
        max_dd = max((s.drawdown_pct for s in snapshots), default=0.0)
        return_pct = ((end_equity - start_equity) / start_equity) if start_equity > 0 else 0.0

        return {
            "start_equity": start_equity,
            "end_equity": end_equity,
            "max_drawdown": max_dd,
            "return_pct": return_pct,
            "snapshots_count": len(snapshots),
        }

    def _per_strategy(
        self,
        trades: list[TradeRecord],
        signals: list[SignalRecord],
    ) -> dict[str, dict[str, float | int]]:
        strategies = set(t.strategy_name for t in trades) | set(s.strategy_name for s in signals)

        result: dict[str, dict[str, float | int]] = {}
        for strat in strategies:
            strat_trades = [t for t in trades if t.strategy_name == strat]
            strat_signals = [s for s in signals if s.strategy_name == strat]

            wins = len([t for t in strat_trades if t.realized_pnl > 0])
            total_trades = len(strat_trades)
            win_rate = wins / total_trades if total_trades > 0 else 0.0
            total_pnl = sum(t.realized_pnl for t in strat_trades)

            result[strat] = {
                "trades": total_trades,
                "signals": len(strat_signals),
                "win_rate": win_rate,
                "total_pnl": total_pnl,
            }

        return result
