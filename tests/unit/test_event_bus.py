import asyncio

import pytest

from core.event_bus import Event, EventBus, EventType


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


async def test_subscribe_and_publish(event_bus: EventBus) -> None:
    received_events: list[Event] = []

    async def handler(event: Event) -> None:
        received_events.append(event)

    event_bus.subscribe(EventType.SIGNAL, handler)
    await event_bus.start()

    event = Event(event_type=EventType.SIGNAL, source="test", payload={"action": "buy"})
    await event_bus.publish(event)
    await asyncio.sleep(0.1)

    assert len(received_events) == 1
    assert received_events[0].payload["action"] == "buy"
    await event_bus.stop()


async def test_unsubscribe(event_bus: EventBus) -> None:
    received_events: list[Event] = []

    async def handler(event: Event) -> None:
        received_events.append(event)

    event_bus.subscribe(EventType.SIGNAL, handler)
    event_bus.unsubscribe(EventType.SIGNAL, handler)
    await event_bus.start()

    await event_bus.publish(Event(event_type=EventType.SIGNAL, source="test"))
    await asyncio.sleep(0.1)

    assert len(received_events) == 0
    await event_bus.stop()


async def test_multiple_subscribers(event_bus: EventBus) -> None:
    counter = {"count": 0}

    async def handler_a(event: Event) -> None:
        counter["count"] += 1

    async def handler_b(event: Event) -> None:
        counter["count"] += 10

    event_bus.subscribe(EventType.ORDER_FILLED, handler_a)
    event_bus.subscribe(EventType.ORDER_FILLED, handler_b)
    await event_bus.start()

    await event_bus.publish(Event(event_type=EventType.ORDER_FILLED, source="test"))
    await asyncio.sleep(0.1)

    assert counter["count"] == 11
    await event_bus.stop()


async def test_subscribe_all(event_bus: EventBus) -> None:
    received: list[EventType] = []

    async def global_handler(event: Event) -> None:
        received.append(event.event_type)

    event_bus.subscribe_all(global_handler)
    await event_bus.start()

    await event_bus.publish(Event(event_type=EventType.SIGNAL, source="test"))
    await event_bus.publish(Event(event_type=EventType.ORDER_FILLED, source="test"))
    await asyncio.sleep(0.1)

    assert EventType.SIGNAL in received
    assert EventType.ORDER_FILLED in received
    await event_bus.stop()


async def test_error_handling_in_dispatch(event_bus: EventBus) -> None:
    error_events: list[Event] = []

    async def failing_handler(event: Event) -> None:
        raise ValueError("handler crashed")

    async def error_handler(event: Event) -> None:
        error_events.append(event)

    event_bus.subscribe(EventType.SIGNAL, failing_handler)
    event_bus.subscribe(EventType.ERROR, error_handler)
    await event_bus.start()

    await event_bus.publish(Event(event_type=EventType.SIGNAL, source="test"))
    await asyncio.sleep(0.1)

    assert len(error_events) == 1
    assert error_events[0].payload["error_type"] == "ValueError"
    await event_bus.stop()


async def test_pending_events(event_bus: EventBus) -> None:
    event_bus.publish_nowait(Event(event_type=EventType.SIGNAL, source="test"))
    event_bus.publish_nowait(Event(event_type=EventType.SIGNAL, source="test"))
    assert event_bus.pending_events == 2
