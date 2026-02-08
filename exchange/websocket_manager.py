import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from exchange.bybit_client import BybitClient
from exchange.models import Candle, Ticker
from core.event_bus import Event, EventBus, EventType

logger = structlog.get_logger("websocket_manager")

WsHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class WebSocketManager:
    def __init__(self, client: BybitClient, event_bus: EventBus) -> None:
        self._client = client
        self._event_bus = event_bus
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    async def start(self) -> None:
        self._running = True
        await logger.ainfo("websocket_manager_started")

    async def stop(self) -> None:
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        await logger.ainfo("websocket_manager_stopped")

    def subscribe_ticker(self, symbol: str) -> None:
        name = f"ticker:{symbol}"
        if name not in self._tasks:
            self._tasks[name] = asyncio.create_task(
                self._watch_ticker_loop(symbol)
            )

    def subscribe_ohlcv(self, symbol: str, timeframe: str = "1m") -> None:
        name = f"ohlcv:{symbol}:{timeframe}"
        if name not in self._tasks:
            self._tasks[name] = asyncio.create_task(
                self._watch_ohlcv_loop(symbol, timeframe)
            )

    def subscribe_orderbook(self, symbol: str) -> None:
        name = f"orderbook:{symbol}"
        if name not in self._tasks:
            self._tasks[name] = asyncio.create_task(
                self._watch_orderbook_loop(symbol)
            )

    def subscribe_orders(self, symbol: str | None = None) -> None:
        name = f"orders:{symbol or 'all'}"
        if name not in self._tasks:
            self._tasks[name] = asyncio.create_task(
                self._watch_orders_loop(symbol)
            )

    def subscribe_positions(self, symbols: list[str] | None = None) -> None:
        name = f"positions:{','.join(symbols) if symbols else 'all'}"
        if name not in self._tasks:
            self._tasks[name] = asyncio.create_task(
                self._watch_positions_loop(symbols)
            )

    def subscribe_balance(self) -> None:
        name = "balance"
        if name not in self._tasks:
            self._tasks[name] = asyncio.create_task(
                self._watch_balance_loop()
            )

    async def _watch_ticker_loop(self, symbol: str) -> None:
        while self._running:
            try:
                data = await self._client.exchange.watch_ticker(symbol)
                self._event_bus.publish_nowait(Event(
                    event_type=EventType.TICKER,
                    source="websocket",
                    payload={"symbol": symbol, "data": data},
                ))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("ws_ticker_error", symbol=symbol, error=str(exc))
                await asyncio.sleep(1)

    async def _watch_ohlcv_loop(self, symbol: str, timeframe: str) -> None:
        while self._running:
            try:
                data = await self._client.exchange.watch_ohlcv(symbol, timeframe)
                self._event_bus.publish_nowait(Event(
                    event_type=EventType.KLINE,
                    source="websocket",
                    payload={"symbol": symbol, "timeframe": timeframe, "data": data},
                ))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if "is not supported yet" in str(exc):
                    await logger.ainfo("ws_ohlcv_not_supported", symbol=symbol)
                    break
                await logger.aerror("ws_ohlcv_error", symbol=symbol, error=str(exc))
                await asyncio.sleep(1)

    async def _watch_orderbook_loop(self, symbol: str) -> None:
        while self._running:
            try:
                data = await self._client.exchange.watch_order_book(symbol)
                self._event_bus.publish_nowait(Event(
                    event_type=EventType.ORDERBOOK,
                    source="websocket",
                    payload={"symbol": symbol, "data": data},
                ))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await logger.aerror("ws_orderbook_error", symbol=symbol, error=str(exc))
                await asyncio.sleep(1)

    async def _watch_orders_loop(self, symbol: str | None) -> None:
        while self._running:
            try:
                data = await self._client.exchange.watch_orders(symbol)
                for order in data:
                    event_type = _order_status_to_event(order.get("status", ""))
                    self._event_bus.publish_nowait(Event(
                        event_type=event_type,
                        source="websocket",
                        payload={"data": order},
                    ))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if "is not supported yet" in str(exc):
                    await logger.ainfo("ws_orders_not_supported")
                    break
                await logger.aerror("ws_orders_error", error=str(exc))
                await asyncio.sleep(1)

    async def _watch_positions_loop(self, symbols: list[str] | None) -> None:
        while self._running:
            try:
                data = await self._client.exchange.watch_positions(symbols)
                for pos in data:
                    self._event_bus.publish_nowait(Event(
                        event_type=EventType.POSITION_UPDATED,
                        source="websocket",
                        payload={"data": pos},
                    ))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if "is not supported yet" in str(exc):
                    await logger.ainfo("ws_positions_not_supported")
                    break
                await logger.aerror("ws_positions_error", error=str(exc))
                await asyncio.sleep(1)

    async def _watch_balance_loop(self) -> None:
        while self._running:
            try:
                data = await self._client.exchange.watch_balance()
                self._event_bus.publish_nowait(Event(
                    event_type=EventType.PORTFOLIO_UPDATE,
                    source="websocket",
                    payload={"data": data},
                ))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if "is not supported yet" in str(exc):
                    await logger.ainfo("ws_balance_not_supported")
                    break
                await logger.aerror("ws_balance_error", error=str(exc))
                await asyncio.sleep(1)

    @property
    def active_subscriptions(self) -> list[str]:
        return [name for name, task in self._tasks.items() if not task.done()]


def _order_status_to_event(status: str) -> EventType:
    status_map = {
        "open": EventType.ORDER_PLACED,
        "closed": EventType.ORDER_FILLED,
        "canceled": EventType.ORDER_CANCELLED,
        "rejected": EventType.ORDER_REJECTED,
    }
    return status_map.get(status, EventType.ORDER_PLACED)
