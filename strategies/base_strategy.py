from abc import ABC, abstractmethod
from decimal import Decimal
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, Field

from data.models import OrderSide


class SignalDirection(StrEnum):
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    NEUTRAL = "neutral"


class Signal(BaseModel):
    symbol: str
    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    strategy_name: str
    entry_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    metadata: dict[str, float] = Field(default_factory=dict)


class StrategyState(StrEnum):
    IDLE = "idle"
    LONG = "long"
    SHORT = "short"


class BaseStrategy(ABC):
    def __init__(self, name: str, symbols: list[str]) -> None:
        self._name = name
        self._symbols = symbols
        self._states: dict[str, StrategyState] = {s: StrategyState.IDLE for s in symbols}
        self._enabled = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def symbols(self) -> list[str]:
        return self._symbols

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def get_state(self, symbol: str) -> StrategyState:
        return self._states.get(symbol, StrategyState.IDLE)

    def set_state(self, symbol: str, state: StrategyState) -> None:
        self._states[symbol] = state

    @abstractmethod
    def min_candles_required(self) -> int:
        ...

    @abstractmethod
    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        ...

    def should_enter_long(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if self.get_state(symbol) != StrategyState.IDLE:
            return None
        signal = self.generate_signal(symbol, df)
        if signal and signal.direction == SignalDirection.LONG:
            return signal
        return None

    def should_enter_short(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if self.get_state(symbol) != StrategyState.IDLE:
            return None
        signal = self.generate_signal(symbol, df)
        if signal and signal.direction == SignalDirection.SHORT:
            return signal
        return None

    def should_exit(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        state = self.get_state(symbol)
        if state == StrategyState.IDLE:
            return None
        signal = self.generate_signal(symbol, df)
        if not signal:
            return None
        if state == StrategyState.LONG and signal.direction == SignalDirection.CLOSE_LONG:
            return signal
        if state == StrategyState.SHORT and signal.direction == SignalDirection.CLOSE_SHORT:
            return signal
        return None
