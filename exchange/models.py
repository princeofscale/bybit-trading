from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from data.models import MarketCategory, OrderSide, OrderStatus, OrderType, PositionSide, TimeInForce
from utils.time_utils import utc_now_ms


class InstrumentInfo(BaseModel):
    symbol: str
    ccxt_symbol: str
    category: MarketCategory
    base_coin: str
    quote_coin: str
    min_qty: Decimal
    max_qty: Decimal
    qty_step: Decimal
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    min_notional: Decimal = Decimal("0")
    max_leverage: Decimal = Decimal("1")


class Ticker(BaseModel):
    symbol: str
    last_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    high_24h: Decimal
    low_24h: Decimal
    volume_24h: Decimal
    turnover_24h: Decimal
    open_interest: Decimal = Decimal("0")
    funding_rate: Decimal = Decimal("0")
    next_funding_time: int = 0
    mark_price: Decimal = Decimal("0")
    index_price: Decimal = Decimal("0")
    timestamp: int = Field(default_factory=utc_now_ms)


class Candle(BaseModel):
    symbol: str
    timeframe: str
    open_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool = True


class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    position_idx: int = 0
    client_order_id: str = ""
    category: MarketCategory = MarketCategory.LINEAR


class OrderResult(BaseModel):
    order_id: str
    client_order_id: str = ""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    avg_fill_price: Decimal | None = None
    filled_qty: Decimal = Decimal("0")
    remaining_qty: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.NEW
    fee: Decimal = Decimal("0")
    fee_currency: str = ""
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    created_at: int = Field(default_factory=utc_now_ms)
    updated_at: int = Field(default_factory=utc_now_ms)


class InFlightOrderStatus(StrEnum):
    PENDING_CREATE = "pending_create"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    PENDING_CANCEL = "pending_cancel"
    DONE = "done"


class InFlightOrder(BaseModel):
    client_order_id: str
    exchange_order_id: str = ""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    filled_qty: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    fee: Decimal = Decimal("0")
    status: InFlightOrderStatus = InFlightOrderStatus.PENDING_CREATE
    strategy_name: str = ""
    created_at: int = Field(default_factory=utc_now_ms)
    last_update: int = Field(default_factory=utc_now_ms)


class Position(BaseModel):
    symbol: str
    side: PositionSide
    size: Decimal
    entry_price: Decimal
    mark_price: Decimal = Decimal("0")
    liquidation_price: Decimal | None = None
    leverage: Decimal = Decimal("1")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    trailing_stop: Decimal | None = None
    position_idx: int = 0
    updated_at: int = Field(default_factory=utc_now_ms)


class CoinBalance(BaseModel):
    coin: str
    equity: Decimal
    wallet_balance: Decimal
    available_to_withdraw: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    usd_value: Decimal = Decimal("0")


class AccountBalance(BaseModel):
    total_equity: Decimal
    total_wallet_balance: Decimal
    total_available_balance: Decimal
    total_margin_balance: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_initial_margin: Decimal = Decimal("0")
    total_maintenance_margin: Decimal = Decimal("0")
    coin_balances: dict[str, CoinBalance] = Field(default_factory=dict)
    updated_at: int = Field(default_factory=utc_now_ms)
