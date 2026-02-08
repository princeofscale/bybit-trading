from decimal import Decimal

from data.models import OrderSide, OrderStatus, OrderType, PositionSide
from exchange.models import (
    InFlightOrder,
    InFlightOrderStatus,
    InstrumentInfo,
    OrderRequest,
    OrderResult,
    Position,
    Ticker,
    Candle,
    AccountBalance,
    CoinBalance,
    MarketCategory,
)


def test_order_request_defaults() -> None:
    req = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )
    assert req.reduce_only is False
    assert req.position_idx == 0
    assert req.price is None


def test_order_result_defaults() -> None:
    result = OrderResult(
        order_id="123",
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("30000"),
    )
    assert result.status == OrderStatus.NEW
    assert result.filled_qty == Decimal("0")
    assert result.fee == Decimal("0")


def test_in_flight_order_lifecycle() -> None:
    order = InFlightOrder(
        client_order_id="abc-123",
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
    )
    assert order.status == InFlightOrderStatus.PENDING_CREATE
    order.status = InFlightOrderStatus.OPEN
    order.exchange_order_id = "exch-456"
    assert order.exchange_order_id == "exch-456"
    order.filled_qty = Decimal("0.005")
    order.status = InFlightOrderStatus.PARTIALLY_FILLED
    order.filled_qty = Decimal("0.01")
    order.status = InFlightOrderStatus.DONE
    assert order.status == InFlightOrderStatus.DONE


def test_position_model() -> None:
    pos = Position(
        symbol="ETH/USDT:USDT",
        side=PositionSide.LONG,
        size=Decimal("1.0"),
        entry_price=Decimal("2000"),
        leverage=Decimal("3"),
    )
    assert pos.unrealized_pnl == Decimal("0")
    assert pos.stop_loss is None


def test_instrument_info() -> None:
    info = InstrumentInfo(
        symbol="BTCUSDT",
        ccxt_symbol="BTC/USDT:USDT",
        category=MarketCategory.LINEAR,
        base_coin="BTC",
        quote_coin="USDT",
        min_qty=Decimal("0.001"),
        max_qty=Decimal("100"),
        qty_step=Decimal("0.001"),
        min_price=Decimal("0.01"),
        max_price=Decimal("1000000"),
        tick_size=Decimal("0.01"),
        max_leverage=Decimal("100"),
    )
    assert info.min_notional == Decimal("0")


def test_ticker_model() -> None:
    ticker = Ticker(
        symbol="BTC/USDT:USDT",
        last_price=Decimal("30000"),
        bid_price=Decimal("29999"),
        ask_price=Decimal("30001"),
        high_24h=Decimal("31000"),
        low_24h=Decimal("29000"),
        volume_24h=Decimal("1000"),
        turnover_24h=Decimal("30000000"),
    )
    assert ticker.funding_rate == Decimal("0")


def test_candle_model() -> None:
    candle = Candle(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        open_time=1700000000000,
        open=Decimal("30000"),
        high=Decimal("30100"),
        low=Decimal("29900"),
        close=Decimal("30050"),
        volume=Decimal("100"),
    )
    assert candle.is_closed is True


def test_account_balance() -> None:
    balance = AccountBalance(
        total_equity=Decimal("10000"),
        total_wallet_balance=Decimal("10000"),
        total_available_balance=Decimal("8000"),
    )
    assert balance.total_unrealized_pnl == Decimal("0")
