import asyncio

import structlog

from config.settings import AppSettings
from core.event_bus import Event, EventBus, EventType
from core.state_manager import BotState, StateManager
from database.connection import Database
from exchange.rate_limiter import RateLimiter
from monitoring.logger import setup_logging


class TradingEngine:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._event_bus = EventBus()
        self._state_manager = StateManager()
        self._database = Database(settings.database)
        self._rate_limiter = RateLimiter()
        self._logger = structlog.get_logger("engine")
        self._shutdown_event = asyncio.Event()

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def state_manager(self) -> StateManager:
        return self._state_manager

    @property
    def database(self) -> Database:
        return self._database

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    async def start(self) -> None:
        setup_logging(self._settings.log_level, self._settings.log_format)
        await self._logger.ainfo("engine_starting", environment=self._settings.environment)

        await self._database.connect()
        await self._logger.ainfo("database_connected")

        await self._event_bus.start()
        await self._logger.ainfo("event_bus_started")

        self._event_bus.subscribe(EventType.ERROR, self._on_error)

        await self._state_manager.transition_to(BotState.RUNNING)
        self._event_bus.publish_nowait(Event(
            event_type=EventType.SYSTEM_START,
            source="engine",
        ))
        await self._logger.ainfo("engine_running")

    async def stop(self) -> None:
        await self._logger.ainfo("engine_stopping")
        await self._state_manager.transition_to(BotState.STOPPING)

        self._event_bus.publish_nowait(Event(
            event_type=EventType.SYSTEM_STOP,
            source="engine",
        ))

        await self._event_bus.stop()
        await self._database.disconnect()
        await self._state_manager.transition_to(BotState.STOPPED)
        await self._logger.ainfo("engine_stopped")

    async def run(self) -> None:
        await self.start()
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def _on_error(self, event: Event) -> None:
        await self._logger.aerror(
            "engine_error",
            source=event.payload.get("original_event_type", "unknown"),
            error_type=event.payload.get("error_type", "unknown"),
            error_message=event.payload.get("error_message", ""),
        )
