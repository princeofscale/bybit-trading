from decimal import Decimal

import pandas as pd

from indicators.volatility import atr, bollinger_bands
from indicators.volume import volume_ratio
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class BreakoutStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        atr_sl_multiplier: float = 1.5,
        atr_tp_multiplier: float = 3.0,
        volume_sma_period: int = 20,
        volume_threshold: float = 1.5,
        min_confidence: float = 0.5,
    ) -> None:
        super().__init__("breakout", symbols)
        self._bb_period = bb_period
        self._bb_std = bb_std
        self._atr_period = atr_period
        self._atr_sl_mult = atr_sl_multiplier
        self._atr_tp_mult = atr_tp_multiplier
        self._vol_sma = volume_sma_period
        self._vol_threshold = volume_threshold
        self._min_confidence = min_confidence

    def min_candles_required(self) -> int:
        return max(self._bb_period, self._vol_sma) + 5

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_candles_required():
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        bb = bollinger_bands(close, self._bb_period, self._bb_std)
        atr_val = atr(high, low, close, self._atr_period).iloc[-1]
        vol_r = volume_ratio(df["volume"], self._vol_sma).iloc[-1]

        current_price = close.iloc[-1]
        prev_price = close.iloc[-2]
        bb_upper = bb["upper"].iloc[-1]
        bb_lower = bb["lower"].iloc[-1]
        bb_width = bb["width"].iloc[-1]

        state = self.get_state(symbol)

        if state == StrategyState.LONG:
            if current_price < bb["middle"].iloc[-1]:
                return Signal(
                    symbol=symbol, direction=SignalDirection.CLOSE_LONG,
                    confidence=0.6, strategy_name=self._name,
                )
            return None
        if state == StrategyState.SHORT:
            if current_price > bb["middle"].iloc[-1]:
                return Signal(
                    symbol=symbol, direction=SignalDirection.CLOSE_SHORT,
                    confidence=0.6, strategy_name=self._name,
                )
            return None

        upside_breakout = prev_price <= bb_upper and current_price > bb_upper
        downside_breakout = prev_price >= bb_lower and current_price < bb_lower

        if not upside_breakout and not downside_breakout:
            return None

        volume_confirmed = vol_r >= self._vol_threshold
        if not volume_confirmed:
            return None

        confidence = self._calc_confidence(bb_width, vol_r)
        if confidence < self._min_confidence:
            return None

        sl_dist = atr_val * self._atr_sl_mult
        tp_dist = atr_val * self._atr_tp_mult

        if upside_breakout:
            return Signal(
                symbol=symbol, direction=SignalDirection.LONG,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(current_price - sl_dist, 2))),
                take_profit=Decimal(str(round(current_price + tp_dist, 2))),
                metadata={"bb_width": bb_width, "vol_ratio": vol_r},
            )

        return Signal(
            symbol=symbol, direction=SignalDirection.SHORT,
            confidence=confidence, strategy_name=self._name,
            entry_price=Decimal(str(round(current_price, 2))),
            stop_loss=Decimal(str(round(current_price + sl_dist, 2))),
            take_profit=Decimal(str(round(current_price - tp_dist, 2))),
            metadata={"bb_width": bb_width, "vol_ratio": vol_r},
        )

    def _calc_confidence(self, bb_width: float, vol_ratio: float) -> float:
        squeeze_score = max(1.0 - bb_width * 10, 0.0)
        vol_score = min(vol_ratio / 3.0, 1.0)
        return 0.4 * squeeze_score + 0.6 * vol_score
