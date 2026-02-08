from decimal import Decimal

import structlog

from data.models import PositionSide
from exchange.models import Position
from exchange.rest_api import RestApi

logger = structlog.get_logger("position_manager")


class PositionManager:
    def __init__(self, rest_api: RestApi) -> None:
        self._rest_api = rest_api
        self._positions: dict[str, Position] = {}

    async def sync_positions(self, symbols: list[str] | None = None) -> list[Position]:
        positions = await self._rest_api.fetch_positions(symbols)
        self._positions.clear()
        for pos in positions:
            if pos.size > 0:
                self._positions[pos.symbol] = pos
        await logger.ainfo("positions_synced", count=len(self._positions))
        return positions

    def update_position(self, position: Position) -> None:
        if position.size > 0:
            self._positions[position.symbol] = position
        elif position.symbol in self._positions:
            del self._positions[position.symbol]

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def get_all_positions(self) -> list[Position]:
        return list(self._positions.values())

    def has_position(self, symbol: str) -> bool:
        return symbol in self._positions

    @property
    def open_position_count(self) -> int:
        return len(self._positions)

    @property
    def total_unrealized_pnl(self) -> Decimal:
        return sum((p.unrealized_pnl for p in self._positions.values()), Decimal("0"))

    @property
    def total_position_value(self) -> Decimal:
        return sum(
            (p.size * p.entry_price for p in self._positions.values()),
            Decimal("0"),
        )

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._rest_api.set_leverage(symbol, leverage)
        pos = self._positions.get(symbol)
        if pos:
            pos.leverage = Decimal(str(leverage))
        await logger.ainfo("leverage_set", symbol=symbol, leverage=leverage)

    def get_long_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.side == PositionSide.LONG]

    def get_short_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.side == PositionSide.SHORT]
