from decimal import Decimal

import pandas as pd

from indicators.momentum import rsi
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
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.5,
        volume_sma_period: int = 20,
        volume_threshold: float = 1.5,
        rsi_period: int = 14,
        min_confidence: float = 0.55,
        squeeze_lookback: int = 10,
    ) -> None:
        super().__init__("breakout", symbols)
        self._bb_period = bb_period
        self._bb_std = bb_std
        self._atr_period = atr_period
        self._atr_sl_mult = atr_sl_multiplier
        self._atr_tp_mult = atr_tp_multiplier
        self._vol_sma = volume_sma_period
        self._vol_threshold = volume_threshold
        self._rsi_period = rsi_period
        self._min_confidence = min_confidence
        self._squeeze_lookback = squeeze_lookback

    def min_candles_required(self) -> int:
        return max(self._bb_period, self._vol_sma, self._rsi_period) + 15

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_candles_required():
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        bb = bollinger_bands(close, self._bb_period, self._bb_std)
        atr_val = atr(high, low, close, self._atr_period).iloc[-1]
        vol_r = volume_ratio(df["volume"], self._vol_sma).iloc[-1]
        rsi_val = rsi(close, self._rsi_period).iloc[-1]

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

        if upside_breakout and rsi_val > 80:
            return None
        if downside_breakout and rsi_val < 20:
            return None

        was_squeezed = self._check_squeeze(bb["width"], self._squeeze_lookback)

        confidence = self._calc_confidence(bb_width, vol_r, rsi_val, was_squeezed)
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
                metadata={
                    "bb_width": bb_width, "vol_ratio": vol_r,
                    "rsi": rsi_val, "was_squeezed": float(was_squeezed),
                },
            )

        return Signal(
            symbol=symbol, direction=SignalDirection.SHORT,
            confidence=confidence, strategy_name=self._name,
            entry_price=Decimal(str(round(current_price, 2))),
            stop_loss=Decimal(str(round(current_price + sl_dist, 2))),
            take_profit=Decimal(str(round(current_price - tp_dist, 2))),
            metadata={
                "bb_width": bb_width, "vol_ratio": vol_r,
                "rsi": rsi_val, "was_squeezed": float(was_squeezed),
            },
        )

    def _check_squeeze(self, bb_width: pd.Series, lookback: int) -> bool:
        recent_widths = bb_width.tail(lookback)
        if len(recent_widths) < lookback:
            return False
        avg_width = bb_width.tail(50).mean()
        min_recent = recent_widths.min()
        return min_recent < avg_width * 0.6

    def _calc_confidence(
        self, bb_width: float, vol_ratio: float, rsi_val: float, was_squeezed: bool,
    ) -> float:
        squeeze_score = max(1.0 - bb_width * 10, 0.0)
        vol_score = min(vol_ratio / 3.0, 1.0)
        rsi_score = 1.0 - abs(rsi_val - 50) / 50 * 0.3
        squeeze_bonus = 0.15 if was_squeezed else 0.0
        base = 0.3 * squeeze_score + 0.4 * vol_score + 0.15 * rsi_score + squeeze_bonus
        return min(base, 1.0)
