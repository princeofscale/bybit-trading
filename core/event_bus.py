import asyncio
from collections import defaultdict
from enum import StrEnum
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, Field

from utils.time_utils import utc_now_ms


class EventType(StrEnum):
    MARKET_DATA = "market_data"
    KLINE = "kline"
    ORDERBOOK = "orderbook"
    TRADE = "trade"
    TICKER = "ticker"
    SIGNAL = "signal"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    POSITION_OPENED = "position_opened"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"
    RISK_LIMIT_HIT = "risk_limit_hit"
    CIRCUIT_BREAKER = "circuit_breaker"
    DRAWDOWN_ALERT = "drawdown_alert"
    PORTFOLIO_UPDATE = "portfolio_update"
    REBALANCE = "rebalance"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    HEALTH_CHECK = "health_check"
    ERROR = "error"


class Event(BaseModel):
    event_type: EventType
    timestamp: int = Field(default_factory=utc_now_ms)
    source: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._global_subscribers: list[EventHandler] = []
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running: bool = False
        self._processor_task: asyncio.Task[None] | None = None

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._global_subscribers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        handlers = self._subscribers[event_type]
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        await self._event_queue.put(event)

    def publish_nowait(self, event: Event) -> None:
        self._event_queue.put_nowait(event)

    async def start(self) -> None:
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())

    async def stop(self) -> None:
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

    async def _process_events(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0,
                )
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _dispatch(self, event: Event) -> None:
        handlers = self._subscribers.get(event.event_type, []) + self._global_subscribers
        tasks = [asyncio.create_task(handler(event)) for handler in handlers]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    await self._handle_dispatch_error(event, result)

    async def _handle_dispatch_error(self, event: Event, error: Exception) -> None:
        error_event = Event(
            event_type=EventType.ERROR,
            source="event_bus",
            payload={
                "original_event_type": event.event_type,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )
        for handler in self._subscribers.get(EventType.ERROR, []):
            try:
                await handler(error_event)
            except Exception:
                pass

    @property
    def pending_events(self) -> int:
        return self._event_queue.qsize()
