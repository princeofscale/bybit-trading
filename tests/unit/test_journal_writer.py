from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from journal.writer import JournalWriter


@pytest.fixture
async def writer(tmp_path: Path) -> JournalWriter:
    db_path = tmp_path / "test_journal.db"
    w = JournalWriter(db_path)
    await w.initialize()
    yield w
    await w.close()


async def test_initialize_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "journal.db"
    writer = JournalWriter(db_path)
    await writer.initialize()

    assert db_path.exists()

    await writer.close()


async def test_log_signal(writer: JournalWriter) -> None:
    await writer.log_signal(
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        direction="long",
        confidence=0.75,
        strategy_name="ema_crossover",
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("52000"),
        approved=True,
        rejection_reason="",
        session_id="test_session",
    )


async def test_log_order(writer: JournalWriter) -> None:
    await writer.log_order(
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        client_order_id="order_123",
        exchange_order_id="ex_456",
        symbol="BTCUSDT",
        side="Buy",
        order_type="Market",
        quantity=Decimal("0.1"),
        price=None,
        avg_fill_price=Decimal("50000"),
        filled_qty=Decimal("0.1"),
        status="Filled",
        strategy_name="ema_crossover",
        fee=Decimal("5.0"),
        session_id="test_session",
    )


async def test_log_trade(writer: JournalWriter) -> None:
    await writer.log_trade(
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        side="long",
        entry_price=Decimal("50000"),
        exit_price=Decimal("51000"),
        quantity=Decimal("0.1"),
        realized_pnl=Decimal("100"),
        pnl_pct=Decimal("0.02"),
        strategy_name="ema_crossover",
        hold_duration_ms=3600000,
        session_id="test_session",
    )


async def test_log_risk_event(writer: JournalWriter) -> None:
    await writer.log_risk_event(
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        event_type="drawdown_halt",
        reason="Max drawdown exceeded",
        equity_at_event=Decimal("95000"),
        drawdown_pct=Decimal("0.05"),
        session_id="test_session",
    )


async def test_log_equity_snapshot(writer: JournalWriter) -> None:
    await writer.log_equity_snapshot(
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        total_equity=Decimal("100000"),
        available_balance=Decimal("90000"),
        unrealized_pnl=Decimal("1000"),
        open_position_count=3,
        peak_equity=Decimal("105000"),
        drawdown_pct=Decimal("0.048"),
        session_id="test_session",
    )


async def test_log_system_event(writer: JournalWriter) -> None:
    await writer.log_system_event(
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        event_type="system_start",
        message="Bot started",
        metadata={"version": "1.0", "mode": "testnet"},
        session_id="test_session",
    )


async def test_multiple_signals(writer: JournalWriter) -> None:
    for i in range(5):
        await writer.log_signal(
            timestamp=datetime(2024, 1, 1, 12, i, tzinfo=timezone.utc),
            symbol="BTCUSDT",
            direction="long" if i % 2 == 0 else "short",
            confidence=0.6 + i * 0.05,
            strategy_name="ema_crossover",
            entry_price=Decimal(str(50000 + i * 100)),
            stop_loss=Decimal(str(49000 + i * 100)),
            take_profit=Decimal(str(52000 + i * 100)),
            approved=i % 2 == 0,
            rejection_reason="" if i % 2 == 0 else "drawdown_halt",
            session_id="test_session",
        )
