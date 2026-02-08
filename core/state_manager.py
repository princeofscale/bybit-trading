import asyncio
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from utils.time_utils import utc_now_ms


class BotState(StrEnum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class TradingPause(BaseModel):
    reason: str
    paused_at: int = Field(default_factory=utc_now_ms)
    resume_at: int | None = None


class StateManager:
    def __init__(self) -> None:
        self._state = BotState.INITIALIZING
        self._lock = asyncio.Lock()
        self._trading_pauses: list[TradingPause] = []
        self._metadata: dict[str, Any] = {}

    @property
    def state(self) -> BotState:
        return self._state

    @property
    def is_trading_allowed(self) -> bool:
        if self._state != BotState.RUNNING:
            return False
        now = utc_now_ms()
        active_pauses = [
            p for p in self._trading_pauses
            if p.resume_at is None or p.resume_at > now
        ]
        return len(active_pauses) == 0

    async def transition_to(self, new_state: BotState) -> None:
        async with self._lock:
            valid = _VALID_TRANSITIONS.get(self._state, set())
            if new_state not in valid:
                raise InvalidStateTransition(self._state, new_state)
            self._state = new_state

    def add_trading_pause(self, reason: str, duration_ms: int | None = None) -> None:
        resume_at = utc_now_ms() + duration_ms if duration_ms else None
        self._trading_pauses.append(
            TradingPause(reason=reason, resume_at=resume_at)
        )

    def clear_trading_pauses(self) -> None:
        self._trading_pauses.clear()

    @property
    def active_pauses(self) -> list[TradingPause]:
        now = utc_now_ms()
        return [
            p for p in self._trading_pauses
            if p.resume_at is None or p.resume_at > now
        ]

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)


class InvalidStateTransition(Exception):
    def __init__(self, current: BotState, target: BotState) -> None:
        super().__init__(f"Cannot transition from {current} to {target}")
        self.current = current
        self.target = target


_VALID_TRANSITIONS: dict[BotState, set[BotState]] = {
    BotState.INITIALIZING: {BotState.RUNNING, BotState.ERROR, BotState.STOPPED},
    BotState.RUNNING: {BotState.PAUSED, BotState.STOPPING, BotState.ERROR},
    BotState.PAUSED: {BotState.RUNNING, BotState.STOPPING, BotState.ERROR},
    BotState.STOPPING: {BotState.STOPPED, BotState.ERROR},
    BotState.STOPPED: {BotState.INITIALIZING},
    BotState.ERROR: {BotState.INITIALIZING, BotState.STOPPED},
}
