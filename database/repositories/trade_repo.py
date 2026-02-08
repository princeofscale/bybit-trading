from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import TradeRecord


class TradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trade: TradeRecord) -> None:
        self._session.add(trade)
        await self._session.flush()

    async def get_by_order_id(self, order_id: str) -> TradeRecord | None:
        stmt = select(TradeRecord).where(TradeRecord.order_id == order_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_symbol(
        self, symbol: str, limit: int = 100,
    ) -> list[TradeRecord]:
        stmt = (
            select(TradeRecord)
            .where(TradeRecord.symbol == symbol)
            .order_by(TradeRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_strategy(
        self, strategy_name: str, limit: int = 100,
    ) -> list[TradeRecord]:
        stmt = (
            select(TradeRecord)
            .where(TradeRecord.strategy_name == strategy_name)
            .order_by(TradeRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(
        self, since: datetime, limit: int = 500,
    ) -> list[TradeRecord]:
        stmt = (
            select(TradeRecord)
            .where(TradeRecord.created_at >= since)
            .order_by(TradeRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def total_realized_pnl(self, strategy_name: str | None = None) -> float:
        stmt = select(func.coalesce(func.sum(TradeRecord.realized_pnl), 0.0))
        if strategy_name:
            stmt = stmt.where(TradeRecord.strategy_name == strategy_name)
        result = await self._session.execute(stmt)
        return float(result.scalar() or 0.0)

    async def count(self, strategy_name: str | None = None) -> int:
        stmt = select(func.count()).select_from(TradeRecord)
        if strategy_name:
            stmt = stmt.where(TradeRecord.strategy_name == strategy_name)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def win_rate(self, strategy_name: str | None = None) -> float:
        total = await self.count(strategy_name)
        if total == 0:
            return 0.0
        stmt = (
            select(func.count())
            .select_from(TradeRecord)
            .where(TradeRecord.realized_pnl > 0)
        )
        if strategy_name:
            stmt = stmt.where(TradeRecord.strategy_name == strategy_name)
        result = await self._session.execute(stmt)
        wins = result.scalar() or 0
        return wins / total
