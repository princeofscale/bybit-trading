from decimal import Decimal

import pandas as pd

from indicators.momentum import rsi
from indicators.volatility import atr, bollinger_bands
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class MeanReversionStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        atr_sl_multiplier: float = 1.5,
        use_dynamic_thresholds: bool = True,
        min_confidence: float = 0.5,
    ) -> None:
        super().__init__("mean_reversion", symbols)
        self._rsi_period = rsi_period
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._bb_period = bb_period
        self._bb_std = bb_std
        self._atr_period = atr_period
        self._atr_sl_mult = atr_sl_multiplier
        self._dynamic = use_dynamic_thresholds
        self._min_confidence = min_confidence

    def min_candles_required(self) -> int:
        return max(self._rsi_period, self._bb_period) + 10

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_candles_required():
            return None

        close = df["close"]
        rsi_vals = rsi(close, self._rsi_period)
        bb = bollinger_bands(close, self._bb_period, self._bb_std)
        atr_val = atr(df["high"], df["low"], close, self._atr_period).iloc[-1]

        current_rsi = rsi_vals.iloc[-1]
        current_price = close.iloc[-1]
        bb_lower = bb["lower"].iloc[-1]
        bb_upper = bb["upper"].iloc[-1]
        bb_middle = bb["middle"].iloc[-1]

        oversold, overbought = self._get_thresholds(rsi_vals)

        state = self.get_state(symbol)

        if state == StrategyState.LONG and current_rsi > 50:
            return Signal(
                symbol=symbol, direction=SignalDirection.CLOSE_LONG,
                confidence=0.6, strategy_name=self._name,
            )
        if state == StrategyState.SHORT and current_rsi < 50:
            return Signal(
                symbol=symbol, direction=SignalDirection.CLOSE_SHORT,
                confidence=0.6, strategy_name=self._name,
            )

        if current_rsi < oversold and current_price <= bb_lower:
            confidence = self._calc_confidence(current_rsi, oversold, True)
            if confidence < self._min_confidence:
                return None
            sl = current_price - atr_val * self._atr_sl_mult
            tp = bb_middle
            return Signal(
                symbol=symbol, direction=SignalDirection.LONG,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(sl, 2))),
                take_profit=Decimal(str(round(tp, 2))),
                metadata={"rsi": current_rsi, "bb_lower": bb_lower},
            )

        if current_rsi > overbought and current_price >= bb_upper:
            confidence = self._calc_confidence(current_rsi, overbought, False)
            if confidence < self._min_confidence:
                return None
            sl = current_price + atr_val * self._atr_sl_mult
            tp = bb_middle
            return Signal(
                symbol=symbol, direction=SignalDirection.SHORT,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(sl, 2))),
                take_profit=Decimal(str(round(tp, 2))),
                metadata={"rsi": current_rsi, "bb_upper": bb_upper},
            )

        return None

    def _get_thresholds(self, rsi_vals: pd.Series) -> tuple[float, float]:
        if not self._dynamic:
            return self._rsi_oversold, self._rsi_overbought

        recent = rsi_vals.tail(50)
        rsi_mean = recent.mean()
        rsi_std = recent.std()

        oversold = max(rsi_mean - 1.5 * rsi_std, 15.0)
        overbought = min(rsi_mean + 1.5 * rsi_std, 85.0)
        return oversold, overbought

    def _calc_confidence(self, current_rsi: float, threshold: float, is_long: bool) -> float:
        if is_long:
            distance = (threshold - current_rsi) / threshold
        else:
            distance = (current_rsi - threshold) / (100 - threshold)
        return min(0.5 + distance * 0.5, 1.0)
