from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
import structlog

from journal.models import (
    EquitySnapshotRecord,
    OrderRecord,
    RiskEventRecord,
    SignalRecord,
    SystemEventRecord,
    TradeRecord,
)

logger = structlog.get_logger("journal_reader")


class JournalReader:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self) -> None:
        url = f"sqlite+aiosqlite:///{self._db_path}"
        self._engine = create_async_engine(url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False,
        )
        await logger.ainfo("journal_reader_initialized", path=str(self._db_path))

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            await logger.ainfo("journal_reader_closed")

    async def get_signals(
        self,
        session_id: str,
        strategy_name: str | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(SignalRecord).where(SignalRecord.session_id == session_id)
            if strategy_name:
                stmt = stmt.where(SignalRecord.strategy_name == strategy_name)
            if symbol:
                stmt = stmt.where(SignalRecord.symbol == symbol)
            stmt = stmt.order_by(SignalRecord.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_orders(
        self,
        session_id: str,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[OrderRecord]:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(OrderRecord).where(OrderRecord.session_id == session_id)
            if symbol:
                stmt = stmt.where(OrderRecord.symbol == symbol)
            stmt = stmt.order_by(OrderRecord.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_trades(
        self,
        session_id: str,
        strategy_name: str | None = None,
        limit: int = 100,
    ) -> list[TradeRecord]:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(TradeRecord).where(TradeRecord.session_id == session_id)
            if strategy_name:
                stmt = stmt.where(TradeRecord.strategy_name == strategy_name)
            stmt = stmt.order_by(TradeRecord.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_risk_events(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[RiskEventRecord]:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(RiskEventRecord).where(RiskEventRecord.session_id == session_id)
            stmt = stmt.order_by(RiskEventRecord.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_equity_snapshots(
        self,
        session_id: str,
        limit: int = 1000,
    ) -> list[EquitySnapshotRecord]:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(EquitySnapshotRecord).where(
                EquitySnapshotRecord.session_id == session_id,
            )
            stmt = stmt.order_by(EquitySnapshotRecord.timestamp.asc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_system_events(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[SystemEventRecord]:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(SystemEventRecord).where(SystemEventRecord.session_id == session_id)
            stmt = stmt.order_by(SystemEventRecord.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_trades(
        self,
        session_id: str,
        strategy_name: str | None = None,
    ) -> int:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(TradeRecord).where(
                TradeRecord.session_id == session_id,
            )
            if strategy_name:
                stmt = stmt.where(TradeRecord.strategy_name == strategy_name)

            result = await session.execute(stmt)
            return result.scalar_one()

    async def total_pnl(
        self,
        session_id: str,
        strategy_name: str | None = None,
    ) -> Decimal:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")

        async with self._session_factory() as session:
            stmt = select(func.sum(TradeRecord.realized_pnl)).where(
                TradeRecord.session_id == session_id,
            )
            if strategy_name:
                stmt = stmt.where(TradeRecord.strategy_name == strategy_name)

            result = await session.execute(stmt)
            total = result.scalar_one_or_none()
            return Decimal(str(total)) if total else Decimal("0")

    async def count_signals_since(
        self,
        ts_start: datetime,
        ts_end: datetime | None = None,
    ) -> int:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(SignalRecord).where(SignalRecord.timestamp >= ts_start)
            if ts_end:
                stmt = stmt.where(SignalRecord.timestamp < ts_end)
            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)

    async def count_trades_since(
        self,
        ts_start: datetime,
        ts_end: datetime | None = None,
    ) -> int:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(TradeRecord).where(TradeRecord.timestamp >= ts_start)
            if ts_end:
                stmt = stmt.where(TradeRecord.timestamp < ts_end)
            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)

    async def sum_realized_pnl_since(
        self,
        ts_start: datetime,
        ts_end: datetime | None = None,
    ) -> Decimal:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")
        async with self._session_factory() as session:
            stmt = select(func.sum(TradeRecord.realized_pnl)).where(TradeRecord.timestamp >= ts_start)
            if ts_end:
                stmt = stmt.where(TradeRecord.timestamp < ts_end)
            result = await session.execute(stmt)
            total = result.scalar_one_or_none()
            return Decimal(str(total)) if total else Decimal("0")

    async def latest_equity_snapshot(self) -> EquitySnapshotRecord | None:
        if not self._session_factory:
            raise RuntimeError("JournalReader not initialized")
        async with self._session_factory() as session:
            stmt = select(EquitySnapshotRecord).order_by(EquitySnapshotRecord.timestamp.desc()).limit(1)
            result = await session.execute(stmt)
            return result.scalars().first()
