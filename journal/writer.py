from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator

import orjson
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
import structlog

from journal.models import (
    EquitySnapshotRecord,
    JournalBase,
    OrderRecord,
    RiskEventRecord,
    SignalRecord,
    SystemEventRecord,
    TradeRecord,
)

logger = structlog.get_logger("journal_writer")


class JournalWriter:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+aiosqlite:///{self._db_path}"
        self._engine = create_async_engine(url, echo=False)

        async with self._engine.begin() as conn:
            await conn.run_sync(JournalBase.metadata.create_all)

        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False,
        )
        await logger.ainfo("journal_initialized", path=str(self._db_path))

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            await logger.ainfo("journal_closed")

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        if not self._session_factory:
            raise RuntimeError("JournalWriter not initialized")

        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def log_signal(
        self,
        timestamp: datetime,
        symbol: str,
        direction: str,
        confidence: float,
        strategy_name: str,
        entry_price: Decimal | None,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
        approved: bool,
        rejection_reason: str,
        session_id: str,
    ) -> None:
        async with self._session() as session:
            record = SignalRecord(
                timestamp=timestamp,
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                strategy_name=strategy_name,
                entry_price=float(entry_price) if entry_price else None,
                stop_loss=float(stop_loss) if stop_loss else None,
                take_profit=float(take_profit) if take_profit else None,
                approved=approved,
                rejection_reason=rejection_reason,
                session_id=session_id,
            )
            session.add(record)

    async def log_order(
        self,
        timestamp: datetime,
        client_order_id: str,
        exchange_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None,
        avg_fill_price: Decimal | None,
        filled_qty: Decimal,
        status: str,
        strategy_name: str,
        fee: Decimal,
        session_id: str,
    ) -> None:
        async with self._session() as session:
            record = OrderRecord(
                timestamp=timestamp,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=float(quantity),
                price=float(price) if price else None,
                avg_fill_price=float(avg_fill_price) if avg_fill_price else None,
                filled_qty=float(filled_qty),
                status=status,
                strategy_name=strategy_name,
                fee=float(fee),
                session_id=session_id,
            )
            session.add(record)

    async def log_trade(
        self,
        timestamp: datetime,
        symbol: str,
        side: str,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        realized_pnl: Decimal,
        pnl_pct: Decimal,
        strategy_name: str,
        hold_duration_ms: int,
        session_id: str,
    ) -> None:
        async with self._session() as session:
            record = TradeRecord(
                timestamp=timestamp,
                symbol=symbol,
                side=side,
                entry_price=float(entry_price),
                exit_price=float(exit_price),
                quantity=float(quantity),
                realized_pnl=float(realized_pnl),
                pnl_pct=float(pnl_pct),
                strategy_name=strategy_name,
                hold_duration_ms=hold_duration_ms,
                session_id=session_id,
            )
            session.add(record)

    async def log_risk_event(
        self,
        timestamp: datetime,
        event_type: str,
        reason: str,
        equity_at_event: Decimal,
        drawdown_pct: Decimal,
        session_id: str,
    ) -> None:
        async with self._session() as session:
            record = RiskEventRecord(
                timestamp=timestamp,
                event_type=event_type,
                reason=reason,
                equity_at_event=float(equity_at_event),
                drawdown_pct=float(drawdown_pct),
                session_id=session_id,
            )
            session.add(record)

    async def log_equity_snapshot(
        self,
        timestamp: datetime,
        total_equity: Decimal,
        available_balance: Decimal,
        unrealized_pnl: Decimal,
        open_position_count: int,
        peak_equity: Decimal,
        drawdown_pct: Decimal,
        session_id: str,
    ) -> None:
        async with self._session() as session:
            record = EquitySnapshotRecord(
                timestamp=timestamp,
                total_equity=float(total_equity),
                available_balance=float(available_balance),
                unrealized_pnl=float(unrealized_pnl),
                open_position_count=open_position_count,
                peak_equity=float(peak_equity),
                drawdown_pct=float(drawdown_pct),
                session_id=session_id,
            )
            session.add(record)

    async def log_system_event(
        self,
        timestamp: datetime,
        event_type: str,
        message: str,
        metadata: dict[str, str | float | int],
        session_id: str,
    ) -> None:
        async with self._session() as session:
            record = SystemEventRecord(
                timestamp=timestamp,
                event_type=event_type,
                message=message,
                metadata_json=orjson.dumps(metadata).decode(),
                session_id=session_id,
            )
            session.add(record)
