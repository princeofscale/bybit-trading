from decimal import Decimal

import pandas as pd

from indicators.volatility import atr, bollinger_bands
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class GridLevel:
    def __init__(self, price: float, is_buy: bool, filled: bool = False) -> None:
        self.price = price
        self.is_buy = is_buy
        self.filled = filled


class GridTradingStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        num_grids: int = 10,
        grid_spacing_atr: float = 0.5,
        atr_period: int = 14,
        bb_period: int = 20,
        min_confidence: float = 0.5,
    ) -> None:
        super().__init__("grid_trading", symbols)
        self._num_grids = num_grids
        self._grid_spacing_atr = grid_spacing_atr
        self._atr_period = atr_period
        self._bb_period = bb_period
        self._min_confidence = min_confidence
        self._grids: dict[str, list[GridLevel]] = {}

    def min_candles_required(self) -> int:
        return max(self._atr_period, self._bb_period) + 5

    def build_grid(self, symbol: str, center_price: float, atr_val: float) -> list[GridLevel]:
        spacing = atr_val * self._grid_spacing_atr
        half = self._num_grids // 2
        levels = []

        for i in range(-half, half + 1):
            if i == 0:
                continue
            price = center_price + i * spacing
            is_buy = i < 0
            levels.append(GridLevel(price=price, is_buy=is_buy))

        self._grids[symbol] = levels
        return levels

    def get_grid(self, symbol: str) -> list[GridLevel]:
        return self._grids.get(symbol, [])

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_candles_required():
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        current_price = close.iloc[-1]
        prev_price = close.iloc[-2]

        atr_val = atr(high, low, close, self._atr_period).iloc[-1]

        if symbol not in self._grids:
            bb = bollinger_bands(close, self._bb_period)
            center = bb["middle"].iloc[-1]
            self.build_grid(symbol, center, atr_val)

        grid = self._grids[symbol]

        for level in grid:
            if level.filled:
                continue

            crossed_down = prev_price >= level.price > current_price
            crossed_up = prev_price <= level.price < current_price

            if level.is_buy and crossed_down:
                level.filled = True
                sl_dist = atr_val * 2.0
                tp_dist = atr_val * 2.0
                return Signal(
                    symbol=symbol, direction=SignalDirection.LONG,
                    confidence=0.6, strategy_name=self._name,
                    entry_price=Decimal(str(round(level.price, 2))),
                    stop_loss=Decimal(str(round(level.price - sl_dist, 2))),
                    take_profit=Decimal(str(round(level.price + tp_dist, 2))),
                    metadata={"grid_price": level.price, "atr": atr_val},
                )

            if not level.is_buy and crossed_up:
                level.filled = True
                sl_dist = atr_val * 2.0
                tp_dist = atr_val * 2.0
                return Signal(
                    symbol=symbol, direction=SignalDirection.SHORT,
                    confidence=0.6, strategy_name=self._name,
                    entry_price=Decimal(str(round(level.price, 2))),
                    stop_loss=Decimal(str(round(level.price + sl_dist, 2))),
                    take_profit=Decimal(str(round(level.price - tp_dist, 2))),
                    metadata={"grid_price": level.price, "atr": atr_val},
                )

        return None

    def reset_grid(self, symbol: str) -> None:
        self._grids.pop(symbol, None)
