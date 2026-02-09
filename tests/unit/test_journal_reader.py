from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from journal.writer import JournalWriter
from journal.reader import JournalReader


@pytest.fixture
async def populated_journal(tmp_path: Path) -> tuple[Path, str]:
    db_path = tmp_path / "journal.db"
    session_id = "test_session"

    writer = JournalWriter(db_path)
    await writer.initialize()

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
        session_id=session_id,
    )

    await writer.log_signal(
        timestamp=datetime(2024, 1, 1, 12, 1, tzinfo=timezone.utc),
        symbol="ETHUSDT",
        direction="short",
        confidence=0.65,
        strategy_name="mean_reversion",
        entry_price=Decimal("3000"),
        stop_loss=Decimal("3100"),
        take_profit=Decimal("2900"),
        approved=False,
        rejection_reason="circuit_breaker",
        session_id=session_id,
    )

    await writer.log_trade(
        timestamp=datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        side="long",
        entry_price=Decimal("50000"),
        exit_price=Decimal("51000"),
        quantity=Decimal("0.1"),
        realized_pnl=Decimal("100"),
        pnl_pct=Decimal("0.02"),
        strategy_name="ema_crossover",
        hold_duration_ms=3600000,
        session_id=session_id,
    )

    await writer.log_trade(
        timestamp=datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        side="short",
        entry_price=Decimal("51000"),
        exit_price=Decimal("50500"),
        quantity=Decimal("0.1"),
        realized_pnl=Decimal("50"),
        pnl_pct=Decimal("0.01"),
        strategy_name="mean_reversion",
        hold_duration_ms=1800000,
        session_id=session_id,
    )

    await writer.log_equity_snapshot(
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        total_equity=Decimal("100000"),
        available_balance=Decimal("90000"),
        unrealized_pnl=Decimal("0"),
        open_position_count=0,
        peak_equity=Decimal("100000"),
        drawdown_pct=Decimal("0"),
        session_id=session_id,
    )

    await writer.close()

    return db_path, session_id


async def test_get_signals_all(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    signals = await reader.get_signals(session_id)
    assert len(signals) == 2

    await reader.close()


async def test_get_signals_by_strategy(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    signals = await reader.get_signals(session_id, strategy_name="ema_crossover")
    assert len(signals) == 1
    assert signals[0].strategy_name == "ema_crossover"

    await reader.close()


async def test_get_signals_by_symbol(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    signals = await reader.get_signals(session_id, symbol="BTCUSDT")
    assert len(signals) == 1
    assert signals[0].symbol == "BTCUSDT"

    await reader.close()


async def test_get_trades(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    trades = await reader.get_trades(session_id)
    assert len(trades) == 2

    await reader.close()


async def test_get_trades_by_strategy(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    trades = await reader.get_trades(session_id, strategy_name="ema_crossover")
    assert len(trades) == 1
    assert trades[0].strategy_name == "ema_crossover"

    await reader.close()


async def test_count_trades(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    count = await reader.count_trades(session_id)
    assert count == 2

    count_ema = await reader.count_trades(session_id, strategy_name="ema_crossover")
    assert count_ema == 1

    await reader.close()


async def test_total_pnl(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    total = await reader.total_pnl(session_id)
    assert total == Decimal("150")

    total_ema = await reader.total_pnl(session_id, strategy_name="ema_crossover")
    assert total_ema == Decimal("100")

    await reader.close()


async def test_get_equity_snapshots_ordered(populated_journal: tuple[Path, str]) -> None:
    db_path, session_id = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    snapshots = await reader.get_equity_snapshots(session_id)
    assert len(snapshots) == 1
    assert snapshots[0].total_equity == 100000.0

    await reader.close()


async def test_daily_aggregate_methods(populated_journal: tuple[Path, str]) -> None:
    db_path, _ = populated_journal
    reader = JournalReader(db_path)
    await reader.initialize()

    start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
    assert await reader.count_signals_since(start, end) == 2
    assert await reader.count_trades_since(start, end) == 2
    assert await reader.sum_realized_pnl_since(start, end) == Decimal("150")

    snap = await reader.latest_equity_snapshot()
    assert snap is not None
    assert snap.total_equity == 100000.0
    await reader.close()
