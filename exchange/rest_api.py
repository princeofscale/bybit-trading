from decimal import Decimal
from typing import Any

import ccxt.async_support as ccxt
import structlog

from exchange.bybit_client import BybitClient, map_ccxt_error
from exchange.models import (
    AccountBalance,
    Candle,
    CoinBalance,
    InstrumentInfo,
    OrderRequest,
    OrderResult,
    Position,
    Ticker,
)
from exchange.rate_limiter import EndpointCategory, RateLimiter
from data.models import MarketCategory, OrderSide, OrderStatus, OrderType, PositionSide

logger = structlog.get_logger("rest_api")


class RestApi:
    def __init__(self, client: BybitClient, rate_limiter: RateLimiter) -> None:
        self._client = client
        self._rate_limiter = rate_limiter

    async def fetch_ticker(self, symbol: str) -> Ticker:
        await self._rate_limiter.acquire(EndpointCategory.MARKET_DATA)
        try:
            data = await self._client.exchange.fetch_ticker(symbol)
            return _parse_ticker(symbol, data)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_tickers(self, symbols: list[str] | None = None) -> list[Ticker]:
        await self._rate_limiter.acquire(EndpointCategory.MARKET_DATA)
        try:
            data = await self._client.exchange.fetch_tickers(symbols)
            return [_parse_ticker(sym, t) for sym, t in data.items()]
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        since: int | None = None,
        limit: int = 200,
    ) -> list[Candle]:
        await self._rate_limiter.acquire(EndpointCategory.MARKET_DATA)
        try:
            data = await self._client.exchange.fetch_ohlcv(
                symbol, timeframe, since=since, limit=limit,
            )
            return [
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=int(row[0]),
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                )
                for row in data
            ]
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_orderbook(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        await self._rate_limiter.acquire(EndpointCategory.MARKET_DATA)
        try:
            return await self._client.exchange.fetch_order_book(symbol, limit)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_funding_rate(self, symbol: str) -> Decimal:
        await self._rate_limiter.acquire(EndpointCategory.MARKET_DATA)
        try:
            data = await self._client.exchange.fetch_funding_rate(symbol)
            return Decimal(str(data.get("fundingRate", 0)))
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def place_order(self, request: OrderRequest) -> OrderResult:
        await self._rate_limiter.acquire(EndpointCategory.ORDER_CREATE, request.symbol)
        try:
            params = _build_order_params(request)
            result = await self._client.exchange.create_order(
                symbol=request.symbol,
                type=request.order_type.value.lower(),
                side=request.side.value.lower(),
                amount=float(request.quantity),
                price=float(request.price) if request.price else None,
                params=params,
            )
            return _parse_order_result(result)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def cancel_order(self, order_id: str, symbol: str) -> OrderResult:
        await self._rate_limiter.acquire(EndpointCategory.ORDER_CANCEL, symbol)
        try:
            result = await self._client.exchange.cancel_order(order_id, symbol)
            return _parse_order_result(result)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def cancel_all_orders(self, symbol: str) -> None:
        await self._rate_limiter.acquire(EndpointCategory.ORDER_CANCEL_ALL, symbol)
        try:
            await self._client.exchange.cancel_all_orders(symbol)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def amend_order(
        self,
        order_id: str,
        symbol: str,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
    ) -> OrderResult:
        await self._rate_limiter.acquire(EndpointCategory.ORDER_AMEND, symbol)
        try:
            result = await self._client.exchange.edit_order(
                id=order_id,
                symbol=symbol,
                type="limit",
                side="buy",
                amount=float(quantity) if quantity else None,
                price=float(price) if price else None,
            )
            return _parse_order_result(result)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_open_orders(self, symbol: str | None = None) -> list[OrderResult]:
        await self._rate_limiter.acquire(EndpointCategory.ORDER_QUERY)
        try:
            data = await self._client.exchange.fetch_open_orders(symbol)
            return [_parse_order_result(o) for o in data]
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_positions(self, symbols: list[str] | None = None) -> list[Position]:
        await self._rate_limiter.acquire(EndpointCategory.POSITION)
        try:
            data = await self._client.exchange.fetch_positions(symbols)
            return [_parse_position(p) for p in data if float(p.get("contracts", 0)) > 0]
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._rate_limiter.acquire(EndpointCategory.POSITION)
        try:
            await self._client.exchange.set_leverage(leverage, symbol)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def set_position_mode(self, hedge_mode: bool) -> None:
        await self._rate_limiter.acquire(EndpointCategory.POSITION)
        try:
            await self._client.exchange.set_position_mode(hedge_mode)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_balance(self) -> AccountBalance:
        await self._rate_limiter.acquire(EndpointCategory.ACCOUNT)
        try:
            data = await self._client.exchange.fetch_balance()
            return _parse_balance(data)
        except ccxt.BaseError as e:
            raise map_ccxt_error(e) from e

    async def fetch_instrument_info(self, symbol: str) -> InstrumentInfo:
        market = self._client.exchange.market(symbol)
        return InstrumentInfo(
            symbol=market["id"],
            ccxt_symbol=symbol,
            category=MarketCategory.LINEAR if market.get("linear") else MarketCategory.SPOT,
            base_coin=market["base"],
            quote_coin=market["quote"],
            min_qty=Decimal(str(market["limits"]["amount"]["min"] or 0)),
            max_qty=Decimal(str(market["limits"]["amount"]["max"] or 999999)),
            qty_step=Decimal(str(market["precision"]["amount"] or "0.001")),
            min_price=Decimal(str(market["limits"]["price"]["min"] or 0)),
            max_price=Decimal(str(market["limits"]["price"]["max"] or 999999)),
            tick_size=Decimal(str(market["precision"]["price"] or "0.01")),
            max_leverage=Decimal(str(market.get("info", {}).get("leverageFilter", {}).get("maxLeverage", "1"))),
        )


def _build_order_params(request: OrderRequest) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if request.position_idx != 0:
        params["positionIdx"] = request.position_idx
    if request.reduce_only:
        params["reduceOnly"] = True
    if request.client_order_id:
        params["orderLinkId"] = request.client_order_id
    if request.stop_loss:
        params["stopLoss"] = {"triggerPrice": float(request.stop_loss), "type": "market"}
    if request.take_profit:
        params["takeProfit"] = {"triggerPrice": float(request.take_profit), "type": "market"}
    if request.time_in_force == "PostOnly":
        params["timeInForce"] = "PO"
    return params


def _parse_ticker(symbol: str, data: dict[str, Any]) -> Ticker:
    return Ticker(
        symbol=symbol,
        last_price=Decimal(str(data.get("last", 0))),
        bid_price=Decimal(str(data.get("bid", 0))),
        ask_price=Decimal(str(data.get("ask", 0))),
        high_24h=Decimal(str(data.get("high", 0))),
        low_24h=Decimal(str(data.get("low", 0))),
        volume_24h=Decimal(str(data.get("baseVolume", 0))),
        turnover_24h=Decimal(str(data.get("quoteVolume", 0))),
        funding_rate=Decimal(str(data.get("info", {}).get("fundingRate", 0))),
        mark_price=Decimal(str(data.get("info", {}).get("markPrice", 0))),
        index_price=Decimal(str(data.get("info", {}).get("indexPrice", 0))),
        timestamp=int(data.get("timestamp", 0)),
    )


def _parse_order_result(data: dict[str, Any]) -> OrderResult:
    status_map = {
        "open": OrderStatus.NEW,
        "closed": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELLED,
        "expired": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
    }
    return OrderResult(
        order_id=data.get("id", ""),
        client_order_id=data.get("clientOrderId", ""),
        symbol=data.get("symbol", ""),
        side=OrderSide.BUY if data.get("side") == "buy" else OrderSide.SELL,
        order_type=OrderType.LIMIT if data.get("type") == "limit" else OrderType.MARKET,
        quantity=Decimal(str(data.get("amount", 0))),
        price=Decimal(str(data["price"])) if data.get("price") else None,
        avg_fill_price=Decimal(str(data["average"])) if data.get("average") else None,
        filled_qty=Decimal(str(data.get("filled", 0))),
        remaining_qty=Decimal(str(data.get("remaining", 0))),
        status=status_map.get(data.get("status", ""), OrderStatus.NEW),
        fee=Decimal(str(data.get("fee", {}).get("cost", 0))) if data.get("fee") else Decimal("0"),
        fee_currency=data.get("fee", {}).get("currency", "") if data.get("fee") else "",
        created_at=int(data.get("timestamp", 0)),
    )


def _parse_position(data: dict[str, Any]) -> Position:
    side = data.get("side", "")
    return Position(
        symbol=data.get("symbol", ""),
        side=PositionSide.LONG if side == "long" else PositionSide.SHORT if side == "short" else PositionSide.NONE,
        size=Decimal(str(data.get("contracts", 0))),
        entry_price=Decimal(str(data.get("entryPrice", 0))),
        mark_price=Decimal(str(data.get("markPrice", 0))),
        liquidation_price=Decimal(str(data["liquidationPrice"])) if data.get("liquidationPrice") else None,
        leverage=Decimal(str(data.get("leverage", 1))),
        unrealized_pnl=Decimal(str(data.get("unrealizedPnl", 0))),
        realized_pnl=Decimal(str(data.get("info", {}).get("cumRealisedPnl", 0))),
        stop_loss=Decimal(str(data["stopLoss"])) if data.get("stopLoss") else None,
        take_profit=Decimal(str(data["takeProfit"])) if data.get("takeProfit") else None,
        position_idx=int(data.get("info", {}).get("positionIdx", 0)),
    )


def _parse_balance(data: dict[str, Any]) -> AccountBalance:
    total = data.get("total", {})
    free = data.get("free", {})
    usdt_total = Decimal(str(total.get("USDT", 0)))
    usdt_free = Decimal(str(free.get("USDT", 0)))

    return AccountBalance(
        total_equity=usdt_total,
        total_wallet_balance=usdt_total,
        total_available_balance=usdt_free,
    )
