from decimal import Decimal

import pandas as pd

from indicators.momentum import rsi
from indicators.technical import adx, ema, supertrend
from indicators.volatility import atr
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class TrendFollowingStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        fast_ema: int = 21,
        slow_ema: int = 50,
        trend_ema: int = 200,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        rsi_period: int = 14,
        atr_period: int = 14,
        atr_sl_multiplier: float = 2.5,
        atr_tp_multiplier: float = 4.0,
        use_supertrend: bool = True,
        min_confidence: float = 0.5,
    ) -> None:
        super().__init__("trend_following", symbols)
        self._fast = fast_ema
        self._slow = slow_ema
        self._trend = trend_ema
        self._adx_period = adx_period
        self._adx_threshold = adx_threshold
        self._rsi_period = rsi_period
        self._atr_period = atr_period
        self._atr_sl_mult = atr_sl_multiplier
        self._atr_tp_mult = atr_tp_multiplier
        self._use_st = use_supertrend
        self._min_confidence = min_confidence

    def min_candles_required(self) -> int:
        return self._trend + 10

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_candles_required():
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        fast_vals = ema(close, self._fast)
        slow_vals = ema(close, self._slow)
        trend_vals = ema(close, self._trend)
        adx_val, adx_pos, adx_neg = adx(high, low, close, self._adx_period)
        rsi_val = rsi(close, self._rsi_period)
        atr_val = atr(high, low, close, self._atr_period).iloc[-1]

        current_price = close.iloc[-1]
        curr_adx = adx_val.iloc[-1]
        curr_rsi = rsi_val.iloc[-1]

        trending = curr_adx > self._adx_threshold
        uptrend = fast_vals.iloc[-1] > slow_vals.iloc[-1] > trend_vals.iloc[-1]
        downtrend = fast_vals.iloc[-1] < slow_vals.iloc[-1] < trend_vals.iloc[-1]

        st_direction = 1
        if self._use_st:
            _, st_dir = supertrend(high, low, close)
            st_direction = st_dir.iloc[-1]

        state = self.get_state(symbol)

        if state == StrategyState.LONG:
            exit_cond = not uptrend or (self._use_st and st_direction == -1)
            if exit_cond:
                return Signal(
                    symbol=symbol, direction=SignalDirection.CLOSE_LONG,
                    confidence=0.7, strategy_name=self._name,
                )
            return None

        if state == StrategyState.SHORT:
            exit_cond = not downtrend or (self._use_st and st_direction == 1)
            if exit_cond:
                return Signal(
                    symbol=symbol, direction=SignalDirection.CLOSE_SHORT,
                    confidence=0.7, strategy_name=self._name,
                )
            return None

        if not trending:
            return None

        sl_dist = atr_val * self._atr_sl_mult
        tp_dist = atr_val * self._atr_tp_mult

        if uptrend and (not self._use_st or st_direction == 1):
            if curr_rsi > 70:
                return None
            confidence = self._calc_confidence(curr_adx, curr_rsi, True)
            if confidence < self._min_confidence:
                return None
            return Signal(
                symbol=symbol, direction=SignalDirection.LONG,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(current_price - sl_dist, 2))),
                take_profit=Decimal(str(round(current_price + tp_dist, 2))),
                metadata={"adx": curr_adx, "rsi": curr_rsi, "st_dir": st_direction},
            )

        if downtrend and (not self._use_st or st_direction == -1):
            if curr_rsi < 30:
                return None
            confidence = self._calc_confidence(curr_adx, curr_rsi, False)
            if confidence < self._min_confidence:
                return None
            return Signal(
                symbol=symbol, direction=SignalDirection.SHORT,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(current_price + sl_dist, 2))),
                take_profit=Decimal(str(round(current_price - tp_dist, 2))),
                metadata={"adx": curr_adx, "rsi": curr_rsi, "st_dir": st_direction},
            )

        return None

    def _calc_confidence(self, adx_val: float, rsi_val: float, is_long: bool) -> float:
        adx_score = min((adx_val - self._adx_threshold) / 25.0, 1.0)
        if is_long:
            rsi_score = max(0, (rsi_val - 40)) / 30
        else:
            rsi_score = max(0, (60 - rsi_val)) / 30
        return 0.6 * adx_score + 0.4 * min(rsi_score, 1.0)
