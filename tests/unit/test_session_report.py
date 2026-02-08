from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from journal.writer import JournalWriter
from journal.report import SessionReport


@pytest.fixture
async def report_with_data(tmp_path: Path) -> tuple[SessionReport, str]:
    db_path = tmp_path / "journal.db"
    session_id = "test_session"

    writer = JournalWriter(db_path)
    await writer.initialize()

    for i in range(10):
        await writer.log_trade(
            timestamp=datetime(2024, 1, 1, 12 + i, 0, tzinfo=timezone.utc),
            symbol="BTCUSDT",
            side="long" if i % 2 == 0 else "short",
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000" if i % 3 != 0 else "49500"),
            quantity=Decimal("0.1"),
            realized_pnl=Decimal("100" if i % 3 != 0 else "-50"),
            pnl_pct=Decimal("0.02" if i % 3 != 0 else "-0.01"),
            strategy_name="ema_crossover" if i < 5 else "mean_reversion",
            hold_duration_ms=3600000,
            session_id=session_id,
        )

    for i in range(15):
        await writer.log_signal(
            timestamp=datetime(2024, 1, 1, 12, i, tzinfo=timezone.utc),
            symbol="BTCUSDT",
            direction="long",
            confidence=0.7,
            strategy_name="ema_crossover",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"),
            approved=i < 10,
            rejection_reason="" if i < 10 else "circuit_breaker",
            session_id=session_id,
        )

    for i in range(5):
        await writer.log_order(
            timestamp=datetime(2024, 1, 1, 12, i, tzinfo=timezone.utc),
            client_order_id=f"order_{i}",
            exchange_order_id=f"ex_{i}",
            symbol="BTCUSDT",
            side="Buy",
            order_type="Market",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            avg_fill_price=Decimal("50050" if i % 2 == 0 else "50000"),
            filled_qty=Decimal("0.1"),
            status="Filled" if i < 4 else "Cancelled",
            strategy_name="ema_crossover",
            fee=Decimal("5.0"),
            session_id=session_id,
        )

    await writer.log_risk_event(
        timestamp=datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
        event_type="circuit_breaker",
        reason="3 consecutive losses",
        equity_at_event=Decimal("99000"),
        drawdown_pct=Decimal("0.01"),
        session_id=session_id,
    )

    for i in range(3):
        await writer.log_equity_snapshot(
            timestamp=datetime(2024, 1, 1, 12 + i, 0, tzinfo=timezone.utc),
            total_equity=Decimal(str(100000 + i * 500)),
            available_balance=Decimal(str(90000 + i * 500)),
            unrealized_pnl=Decimal(str(i * 100)),
            open_position_count=i,
            peak_equity=Decimal(str(100000 + i * 500)),
            drawdown_pct=Decimal("0"),
            session_id=session_id,
        )

    await writer.close()

    report = SessionReport(db_path)
    await report.initialize()

    return report, session_id


async def test_trade_stats_win_rate(report_with_data: tuple[SessionReport, str]) -> None:
    report, session_id = report_with_data

    result = await report.generate(session_id)
    trade_stats = result["trade_stats"]

    assert trade_stats["total_trades"] == 10
    assert 0.6 <= trade_stats["win_rate"] <= 0.8

    await report.close()


async def test_trade_stats_profit_factor(report_with_data: tuple[SessionReport, str]) -> None:
    report, session_id = report_with_data

    result = await report.generate(session_id)
    trade_stats = result["trade_stats"]

    assert trade_stats["profit_factor"] > 0

    await report.close()


async def test_risk_summary_counts(report_with_data: tuple[SessionReport, str]) -> None:
    report, session_id = report_with_data

    result = await report.generate(session_id)
    risk_summary = result["risk_summary"]

    assert risk_summary["total_signals"] == 15
    assert risk_summary["approved_signals"] == 10
    assert risk_summary["rejected_signals"] == 5
    assert abs(risk_summary["rejection_rate"] - (5 / 15)) < 0.01

    await report.close()


async def test_execution_quality(report_with_data: tuple[SessionReport, str]) -> None:
    report, session_id = report_with_data

    result = await report.generate(session_id)
    exec_quality = result["execution_quality"]

    assert exec_quality["total_orders"] == 5
    assert exec_quality["filled_orders"] == 4
    assert abs(exec_quality["fill_rate"] - 0.8) < 0.01

    await report.close()


async def test_equity_curve(report_with_data: tuple[SessionReport, str]) -> None:
    report, session_id = report_with_data

    result = await report.generate(session_id)
    equity_curve = result["equity_curve"]

    assert equity_curve["start_equity"] == 100000.0
    assert equity_curve["end_equity"] == 101000.0
    assert equity_curve["snapshots_count"] == 3

    await report.close()


async def test_per_strategy_breakdown(report_with_data: tuple[SessionReport, str]) -> None:
    report, session_id = report_with_data

    result = await report.generate(session_id)
    per_strategy = result["per_strategy"]

    assert "ema_crossover" in per_strategy
    assert "mean_reversion" in per_strategy

    ema_stats = per_strategy["ema_crossover"]
    assert ema_stats["trades"] == 5

    await report.close()


async def test_empty_session_returns_zeros(tmp_path: Path) -> None:
    db_path = tmp_path / "empty_journal.db"
    session_id = "empty_session"

    writer = JournalWriter(db_path)
    await writer.initialize()
    await writer.close()

    report = SessionReport(db_path)
    await report.initialize()

    result = await report.generate(session_id)

    assert result["trade_stats"]["total_trades"] == 0
    assert result["trade_stats"]["win_rate"] == 0.0
    assert result["risk_summary"]["total_signals"] == 0
    assert result["execution_quality"]["total_orders"] == 0

    await report.close()
