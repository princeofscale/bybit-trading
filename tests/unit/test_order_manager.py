from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from data.models import MarketCategory, OrderSide, OrderStatus, OrderType
from exchange.errors import InsufficientFundsError
from exchange.models import InFlightOrderStatus, OrderRequest, OrderResult, InstrumentInfo
from exchange.order_manager import OrderManager


@pytest.fixture
def mock_rest_api() -> AsyncMock:
    api = AsyncMock()
    api.fetch_instrument_info = AsyncMock(return_value=InstrumentInfo(
        symbol="BTCUSDT",
        ccxt_symbol="BTC/USDT:USDT",
        category=MarketCategory.LINEAR,
        base_coin="BTC",
        quote_coin="USDT",
        min_qty=Decimal("0.001"),
        max_qty=Decimal("100"),
        qty_step=Decimal("0.001"),
        min_price=Decimal("0.1"),
        max_price=Decimal("1000000"),
        tick_size=Decimal("0.1"),
        min_notional=Decimal("0"),
        max_leverage=Decimal("1"),
    ))
    api.place_order = AsyncMock(return_value=OrderResult(
        order_id="exch-001",
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("30000"),
        status=OrderStatus.NEW,
    ))
    api.cancel_order = AsyncMock(return_value=OrderResult(
        order_id="exch-001",
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        status=OrderStatus.CANCELLED,
    ))
    api.cancel_all_orders = AsyncMock()
    return api


@pytest.fixture
def order_manager(mock_rest_api: AsyncMock) -> OrderManager:
    return OrderManager(mock_rest_api)


async def test_submit_order(order_manager: OrderManager, mock_rest_api: AsyncMock) -> None:
    request = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("30000"),
    )
    in_flight = await order_manager.submit_order(request, "test_strategy")

    assert in_flight.exchange_order_id == "exch-001"
    assert in_flight.status == InFlightOrderStatus.OPEN
    assert in_flight.strategy_name == "test_strategy"
    mock_rest_api.place_order.assert_called_once()
    mock_rest_api.fetch_instrument_info.assert_called_once_with("BTC/USDT:USDT")


async def test_submit_order_generates_client_id(order_manager: OrderManager) -> None:
    request = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )
    in_flight = await order_manager.submit_order(request)
    assert len(in_flight.client_order_id) > 0


async def test_submit_order_clamps_quantity_to_max(order_manager: OrderManager, mock_rest_api: AsyncMock) -> None:
    mock_rest_api.fetch_instrument_info.return_value = InstrumentInfo(
        symbol="ARUSDT",
        ccxt_symbol="AR/USDT:USDT",
        category=MarketCategory.LINEAR,
        base_coin="AR",
        quote_coin="USDT",
        min_qty=Decimal("1"),
        max_qty=Decimal("1000"),
        qty_step=Decimal("1"),
        min_price=Decimal("0.1"),
        max_price=Decimal("1000000"),
        tick_size=Decimal("0.1"),
        min_notional=Decimal("0"),
        max_leverage=Decimal("1"),
    )
    request = OrderRequest(
        symbol="AR/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10000000"),
    )
    await order_manager.submit_order(request)
    placed = mock_rest_api.place_order.call_args.args[0]
    assert placed.quantity == Decimal("1000")


async def test_submit_order_failure(order_manager: OrderManager, mock_rest_api: AsyncMock) -> None:
    mock_rest_api.place_order.side_effect = InsufficientFundsError("no funds")
    request = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("100"),
    )
    with pytest.raises(InsufficientFundsError):
        await order_manager.submit_order(request)

    assert order_manager.in_flight_count == 0


async def test_cancel_order(order_manager: OrderManager, mock_rest_api: AsyncMock) -> None:
    request = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("30000"),
    )
    in_flight = await order_manager.submit_order(request)
    await order_manager.cancel_order(in_flight.client_order_id)

    assert in_flight.status == InFlightOrderStatus.DONE
    mock_rest_api.cancel_order.assert_called_once()


async def test_cancel_unknown_order(order_manager: OrderManager, mock_rest_api: AsyncMock) -> None:
    await order_manager.cancel_order("nonexistent")
    mock_rest_api.cancel_order.assert_not_called()


async def test_cancel_all(order_manager: OrderManager, mock_rest_api: AsyncMock) -> None:
    for _ in range(3):
        await order_manager.submit_order(OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("30000"),
        ))
    await order_manager.cancel_all("BTC/USDT:USDT")
    assert order_manager.in_flight_count == 0


async def test_update_from_exchange(order_manager: OrderManager) -> None:
    request = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("30000"),
    )
    in_flight = await order_manager.submit_order(request)
    order_manager.update_from_exchange(OrderResult(
        order_id="exch-001",
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        filled_qty=Decimal("0.01"),
        status=OrderStatus.FILLED,
    ))
    assert in_flight.status == InFlightOrderStatus.DONE
    assert in_flight.filled_qty == Decimal("0.01")


async def test_get_open_orders(order_manager: OrderManager) -> None:
    await order_manager.submit_order(OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("30000"),
    ))
    await order_manager.submit_order(OrderRequest(
        symbol="ETH/USDT:USDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("2000"),
    ))
    all_open = order_manager.get_open_orders()
    assert len(all_open) == 2
    btc_open = order_manager.get_open_orders("BTC/USDT:USDT")
    assert len(btc_open) == 1


async def test_cleanup_done_orders(order_manager: OrderManager, mock_rest_api: AsyncMock) -> None:
    for i in range(5):
        mock_rest_api.place_order.return_value = OrderResult(
            order_id=f"exch-{i:03d}",
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("30000"),
            status=OrderStatus.NEW,
        )
        in_flight = await order_manager.submit_order(OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("30000"),
        ))
        order_manager.update_from_exchange(OrderResult(
            order_id=f"exch-{i:03d}",
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            filled_qty=Decimal("0.01"),
            status=OrderStatus.FILLED,
        ))
    removed = order_manager.cleanup_done_orders(keep_last=2)
    assert removed == 3
