from decimal import Decimal
from enum import StrEnum

import structlog

logger = structlog.get_logger("stop_loss")


class StopLossType(StrEnum):
    FIXED = "fixed"
    TRAILING = "trailing"
    ATR_BASED = "atr_based"
    TIME_BASED = "time_based"


class StopLossTracker:
    def __init__(
        self,
        entry_price: Decimal,
        stop_price: Decimal,
        is_long: bool,
        sl_type: StopLossType = StopLossType.FIXED,
        trailing_distance: Decimal = Decimal("0"),
    ) -> None:
        self._entry = entry_price
        self._stop = stop_price
        self._is_long = is_long
        self._type = sl_type
        self._trailing_dist = trailing_distance
        self._best_price = entry_price
        self._bars_held = 0

    @property
    def stop_price(self) -> Decimal:
        return self._stop

    @property
    def entry_price(self) -> Decimal:
        return self._entry

    @property
    def is_long(self) -> bool:
        return self._is_long

    @property
    def bars_held(self) -> int:
        return self._bars_held

    def update(self, current_price: Decimal) -> None:
        self._bars_held += 1

        if self._type == StopLossType.TRAILING:
            self._update_trailing(current_price)

    def _update_trailing(self, current_price: Decimal) -> None:
        if self._is_long:
            if current_price > self._best_price:
                self._best_price = current_price
                self._stop = current_price - self._trailing_dist
        else:
            if current_price < self._best_price:
                self._best_price = current_price
                self._stop = current_price + self._trailing_dist

    def is_triggered(self, current_price: Decimal) -> bool:
        if self._is_long:
            return current_price <= self._stop
        return current_price >= self._stop

    def risk_reward_ratio(self, take_profit: Decimal) -> Decimal:
        risk = abs(self._entry - self._stop)
        if risk == 0:
            return Decimal("0")
        reward = abs(take_profit - self._entry)
        return reward / risk


class StopLossManager:
    def __init__(self) -> None:
        self._trackers: dict[str, StopLossTracker] = {}

    def add_stop(
        self,
        order_id: str,
        entry_price: Decimal,
        stop_price: Decimal,
        is_long: bool,
        sl_type: StopLossType = StopLossType.FIXED,
        trailing_distance: Decimal = Decimal("0"),
    ) -> StopLossTracker:
        tracker = StopLossTracker(
            entry_price, stop_price, is_long, sl_type, trailing_distance,
        )
        self._trackers[order_id] = tracker
        return tracker

    def remove_stop(self, order_id: str) -> None:
        self._trackers.pop(order_id, None)

    def get_stop(self, order_id: str) -> StopLossTracker | None:
        return self._trackers.get(order_id)

    def update_all(self, symbol_prices: dict[str, Decimal]) -> list[str]:
        triggered: list[str] = []
        for order_id, tracker in self._trackers.items():
            price = symbol_prices.get(order_id)
            if price is None:
                continue
            tracker.update(price)
            if tracker.is_triggered(price):
                triggered.append(order_id)
        return triggered

    def remove_triggered(self, triggered_ids: list[str]) -> None:
        for oid in triggered_ids:
            self._trackers.pop(oid, None)

    @property
    def active_count(self) -> int:
        return len(self._trackers)

    def create_atr_stop(
        self,
        order_id: str,
        entry_price: Decimal,
        atr_value: Decimal,
        multiplier: Decimal,
        is_long: bool,
    ) -> StopLossTracker:
        distance = atr_value * multiplier
        if is_long:
            stop_price = entry_price - distance
        else:
            stop_price = entry_price + distance
        return self.add_stop(order_id, entry_price, stop_price, is_long)

    def create_trailing_stop(
        self,
        order_id: str,
        entry_price: Decimal,
        trailing_distance: Decimal,
        is_long: bool,
    ) -> StopLossTracker:
        if is_long:
            stop_price = entry_price - trailing_distance
        else:
            stop_price = entry_price + trailing_distance
        return self.add_stop(
            order_id, entry_price, stop_price, is_long,
            StopLossType.TRAILING, trailing_distance,
        )
