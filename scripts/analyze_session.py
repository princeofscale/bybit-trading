import asyncio
import sys
from pathlib import Path

from journal.report import SessionReport


BOX_W = 62
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
WHITE = "\033[97m"


def _header(title: str) -> str:
    pad = BOX_W - len(title) - 4
    left = pad // 2
    right = pad - left
    return f"\n{CYAN}{'═' * left} {BOLD}{title}{RESET}{CYAN} {'═' * right}{RESET}"


def _sep() -> str:
    return f"{DIM}{'─' * BOX_W}{RESET}"


def _val(v: float | int | str, fmt: str = "") -> str:
    if isinstance(v, str):
        return f"{WHITE}{v}{RESET}"
    if fmt == "pct":
        return f"{_color_num(v * 100)}{v * 100:+.2f}%{RESET}"
    if fmt == "usd":
        sign = "+" if v > 0 else ""
        return f"{_color_num(v)}{sign}{v:,.2f} USDT{RESET}"
    if fmt == "rate":
        return f"{_color_num(v - 0.5)}{v * 100:.1f}%{RESET}"
    if isinstance(v, float):
        return f"{WHITE}{v:.4f}{RESET}"
    return f"{WHITE}{v}{RESET}"


def _color_num(v: float) -> str:
    if v > 0:
        return GREEN
    if v < 0:
        return RED
    return WHITE


def _row(label: str, value: str, width: int = 28) -> str:
    return f"  {DIM}{label:<{width}}{RESET} {value}"


def _print_trade_stats(stats: dict) -> None:
    print(_header("СТАТИСТИКА СДЕЛОК"))
    print(_sep())
    print(_row("Всего сделок:", _val(stats.get("total_trades", 0))))
    print(_row("Win rate:", _val(stats.get("win_rate", 0), "rate")))
    print(_row("Profit factor:", _val(stats.get("profit_factor", 0))))
    print(_row("Средний выигрыш:", _val(stats.get("avg_win", 0), "usd")))
    print(_row("Средний убыток:", _val(-abs(stats.get("avg_loss", 0)), "usd")))
    print(_row("Sharpe ratio:", _val(stats.get("sharpe", 0))))
    print(_row("Итого PnL:", _val(stats.get("total_pnl", 0), "usd")))
    print(_sep())


def _print_risk_summary(risk: dict) -> None:
    print(_header("РИСК"))
    print(_sep())
    total_signals = risk.get("total_signals", 0)
    approved = risk.get("approved_signals", 0)
    rejected = risk.get("rejected_signals", 0)
    rejection_rate = risk.get("rejection_rate", 0)
    print(_row("Всего сигналов:", _val(total_signals)))
    print(_row("Одобрено:", f"{GREEN}{approved}{RESET}"))
    print(_row("Отклонено:", f"{RED}{rejected}{RESET}" if rejected > 0 else _val(rejected)))
    print(_row("Rejection rate:", _val(rejection_rate, "rate")))
    print(_row("Risk events:", _val(risk.get("risk_events", 0))))

    skip_keys = {"total_signals", "approved_signals", "rejected_signals", "rejection_rate", "risk_events"}
    extra = {k: v for k, v in risk.items() if k not in skip_keys}
    if extra:
        print(_sep())
        for k, v in extra.items():
            label = k.replace("_", " ").capitalize() + ":"
            print(_row(label, _val(v)))
    print(_sep())


def _print_execution(exec_q: dict) -> None:
    print(_header("КАЧЕСТВО ИСПОЛНЕНИЯ"))
    print(_sep())
    print(_row("Всего ордеров:", _val(exec_q.get("total_orders", 0))))
    print(_row("Исполнено:", _val(exec_q.get("filled_orders", 0))))
    fill_rate = exec_q.get("fill_rate", 0)
    color = GREEN if fill_rate >= 0.9 else YELLOW if fill_rate >= 0.7 else RED
    print(_row("Fill rate:", f"{color}{fill_rate * 100:.1f}%{RESET}"))
    print(_row("Средний slippage:", _val(exec_q.get("avg_slippage", 0), "pct")))
    print(_row("Комиссии:", _val(exec_q.get("total_fees", 0), "usd")))
    print(_sep())


def _print_equity_curve(eq: dict) -> None:
    print(_header("КРИВАЯ ЭКВИТИ"))
    print(_sep())
    start = eq.get("start_equity", 0)
    end = eq.get("end_equity", 0)
    print(_row("Начальное эквити:", _val(start, "usd")))
    print(_row("Конечное эквити:", _val(end, "usd")))
    ret_pct = eq.get("return_pct", 0)
    print(_row("Доходность:", _val(ret_pct, "pct")))
    max_dd = eq.get("max_drawdown", 0)
    dd_color = GREEN if max_dd < 0.05 else YELLOW if max_dd < 0.10 else RED
    print(_row("Макс. просадка:", f"{dd_color}{max_dd * 100:.2f}%{RESET}"))
    print(_row("Снэпшотов:", _val(eq.get("snapshots_count", 0))))
    print(_sep())


def _print_per_strategy(per_strat: dict) -> None:
    print(_header("ПО СТРАТЕГИЯМ"))
    print(_sep())

    if not per_strat:
        print(f"  {DIM}Нет данных по стратегиям{RESET}")
        print(_sep())
        return

    sorted_strats = sorted(per_strat.items(), key=lambda x: x[1].get("total_pnl", 0), reverse=True)

    hdr = f"  {BOLD}{'Стратегия':<22} {'Сделки':>7} {'Win%':>7} {'PnL':>14}{RESET}"
    print(hdr)
    print(f"  {DIM}{'─' * 52}{RESET}")

    for name, stats in sorted_strats:
        trades = stats.get("trades", 0)
        signals = stats.get("signals", 0)
        win_rate = stats.get("win_rate", 0)
        total_pnl = stats.get("total_pnl", 0)

        pnl_color = GREEN if total_pnl > 0 else RED if total_pnl < 0 else WHITE
        wr_color = GREEN if win_rate >= 0.5 else YELLOW if win_rate >= 0.35 else RED

        sign = "+" if total_pnl > 0 else ""
        pnl_str = f"{pnl_color}{sign}{total_pnl:,.2f}{RESET}"
        wr_str = f"{wr_color}{win_rate * 100:.1f}%{RESET}"

        print(f"  {WHITE}{name:<22}{RESET} {trades:>4}/{signals:<3} {wr_str:>15} {pnl_str:>22}")

    print(_sep())


async def main() -> None:
    if len(sys.argv) < 2:
        print(f"\n{BOLD}Usage:{RESET} python scripts/analyze_session.py <journal.db> [session_id]")
        print(f"{DIM}If session_id is not provided, uses the most recent session.{RESET}\n")
        sys.exit(1)

    journal_path = Path(sys.argv[1])
    if not journal_path.exists():
        print(f"\n{RED}Error: Journal file not found: {journal_path}{RESET}")
        sys.exit(1)

    session_id = sys.argv[2] if len(sys.argv) > 2 else ""

    if not session_id:
        from journal.reader import JournalReader
        from sqlalchemy import select, func
        from journal.models import SignalRecord

        reader = JournalReader(journal_path)
        await reader.initialize()

        if reader._session_factory:
            async with reader._session_factory() as session:
                stmt = select(SignalRecord.session_id, func.max(SignalRecord.timestamp)).group_by(
                    SignalRecord.session_id,
                ).order_by(func.max(SignalRecord.timestamp).desc()).limit(1)

                result = await session.execute(stmt)
                row = result.first()
                if row:
                    session_id = row[0]

        await reader.close()

        if not session_id:
            print(f"\n{RED}Error: No sessions found in journal{RESET}")
            sys.exit(1)

    report = SessionReport(journal_path)
    await report.initialize()
    result = await report.generate(session_id)

    print(f"\n{CYAN}{'═' * BOX_W}{RESET}")
    print(f"  {BOLD}SESSION REPORT{RESET}  {DIM}{session_id}{RESET}")
    print(f"{CYAN}{'═' * BOX_W}{RESET}")

    _print_trade_stats(result["trade_stats"])
    _print_risk_summary(result["risk_summary"])
    _print_execution(result["execution_quality"])
    _print_equity_curve(result["equity_curve"])
    _print_per_strategy(result["per_strategy"])

    total_pnl = result["trade_stats"].get("total_pnl", 0)
    pnl_color = GREEN if total_pnl > 0 else RED if total_pnl < 0 else WHITE
    sign = "+" if total_pnl > 0 else ""
    print(f"\n  {BOLD}Итого PnL: {pnl_color}{sign}{total_pnl:,.2f} USDT{RESET}")
    print(f"{CYAN}{'═' * BOX_W}{RESET}\n")

    await report.close()


if __name__ == "__main__":
    asyncio.run(main())
