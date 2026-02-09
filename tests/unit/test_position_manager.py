from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from data.models import PositionSide
from exchange.models import Position
from exchange.position_manager import PositionManager


@pytest.fixture
def mock_rest_api() -> AsyncMock:
    api = AsyncMock()
    api.fetch_positions = AsyncMock(return_value=[
        Position(
            symbol="BTC/USDT:USDT",
            side=PositionSide.LONG,
            size=Decimal("0.1"),
            entry_price=Decimal("30000"),
            leverage=Decimal("3"),
            unrealized_pnl=Decimal("50"),
        ),
        Position(
            symbol="ETH/USDT:USDT",
            side=PositionSide.SHORT,
            size=Decimal("1.0"),
            entry_price=Decimal("2000"),
            leverage=Decimal("2"),
            unrealized_pnl=Decimal("-20"),
        ),
    ])
    api.set_leverage = AsyncMock()
    return api


@pytest.fixture
def position_manager(mock_rest_api: AsyncMock) -> PositionManager:
    return PositionManager(mock_rest_api)


async def test_sync_positions(position_manager: PositionManager) -> None:
    positions = await position_manager.sync_positions()
    assert len(positions) == 2
    assert position_manager.open_position_count == 2


async def test_get_position(position_manager: PositionManager) -> None:
    await position_manager.sync_positions()
    btc = position_manager.get_position("BTC/USDT:USDT")
    assert btc is not None
    assert btc.side == PositionSide.LONG
    assert btc.size == Decimal("0.1")


async def test_has_position(position_manager: PositionManager) -> None:
    await position_manager.sync_positions()
    assert position_manager.has_position("BTC/USDT:USDT") is True
    assert position_manager.has_position("SOL/USDT:USDT") is False


async def test_total_unrealized_pnl(position_manager: PositionManager) -> None:
    await position_manager.sync_positions()
    assert position_manager.total_unrealized_pnl == Decimal("30")


async def test_total_position_value(position_manager: PositionManager) -> None:
    await position_manager.sync_positions()
    expected = Decimal("0.1") * Decimal("30000") + Decimal("1.0") * Decimal("2000")
    assert position_manager.total_position_value == expected


async def test_update_position_add(position_manager: PositionManager) -> None:
    position_manager.update_position(Position(
        symbol="SOL/USDT:USDT",
        side=PositionSide.LONG,
        size=Decimal("10"),
        entry_price=Decimal("100"),
    ))
    assert position_manager.has_position("SOL/USDT:USDT") is True


async def test_update_position_remove(position_manager: PositionManager) -> None:
    await position_manager.sync_positions()
    position_manager.update_position(Position(
        symbol="BTC/USDT:USDT",
        side=PositionSide.NONE,
        size=Decimal("0"),
        entry_price=Decimal("0"),
    ))
    assert position_manager.has_position("BTC/USDT:USDT") is False


async def test_get_long_short_positions(position_manager: PositionManager) -> None:
    await position_manager.sync_positions()
    longs = position_manager.get_long_positions()
    shorts = position_manager.get_short_positions()
    assert len(longs) == 1
    assert len(shorts) == 1
    assert longs[0].symbol == "BTC/USDT:USDT"
    assert shorts[0].symbol == "ETH/USDT:USDT"


async def test_set_leverage(position_manager: PositionManager, mock_rest_api: AsyncMock) -> None:
    await position_manager.sync_positions()
    await position_manager.set_leverage("BTC/USDT:USDT", 5)
    mock_rest_api.set_leverage.assert_called_once_with("BTC/USDT:USDT", 5)
    pos = position_manager.get_position("BTC/USDT:USDT")
    assert pos is not None
    assert pos.leverage == Decimal("5")


async def test_partial_sync_does_not_drop_other_symbols(position_manager: PositionManager, mock_rest_api: AsyncMock) -> None:
    await position_manager.sync_positions()
    mock_rest_api.fetch_positions.return_value = [
        Position(
            symbol="BTC/USDT:USDT",
            side=PositionSide.LONG,
            size=Decimal("0.2"),
            entry_price=Decimal("30100"),
        )
    ]
    await position_manager.sync_positions(["BTC/USDT:USDT"])
    assert position_manager.has_position("ETH/USDT:USDT") is True
    btc = position_manager.get_position("BTC/USDT:USDT")
    assert btc is not None
    assert btc.size == Decimal("0.2")


async def test_partial_sync_removes_only_requested_missing_symbol(
    position_manager: PositionManager,
    mock_rest_api: AsyncMock,
) -> None:
    await position_manager.sync_positions()
    mock_rest_api.fetch_positions.return_value = []
    await position_manager.sync_positions(["BTC/USDT:USDT"])
    assert position_manager.has_position("BTC/USDT:USDT") is False
    assert position_manager.has_position("ETH/USDT:USDT") is True
