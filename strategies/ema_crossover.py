from decimal import Decimal

import pandas as pd

from indicators.technical import adx, ema
from indicators.volatility import atr
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class EmaCrossoverStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        fast_period: int = 9,
        slow_period: int = 21,
        trend_period: int = 200,
        atr_period: int = 14,
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.5,
        adx_min_threshold: float = 20.0,
        volume_confirmation: bool = True,
        volume_sma_period: int = 20,
        min_confidence: float = 0.55,
    ) -> None:
        super().__init__("ema_crossover", symbols)
        self._fast = fast_period
        self._slow = slow_period
        self._trend = trend_period
        self._atr_period = atr_period
        self._atr_sl_mult = atr_sl_multiplier
        self._atr_tp_mult = atr_tp_multiplier
        self._adx_min = adx_min_threshold
        self._volume_confirm = volume_confirmation
        self._volume_sma = volume_sma_period
        self._min_confidence = min_confidence

    def min_candles_required(self) -> int:
        return max(self._trend, self._slow, self._volume_sma) + 10

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_candles_required():
            return None

        close = df["close"]
        fast_ema = ema(close, self._fast)
        slow_ema = ema(close, self._slow)
        trend_ema = ema(close, self._trend)

        prev_fast = fast_ema.iloc[-2]
        prev_slow = slow_ema.iloc[-2]
        curr_fast = fast_ema.iloc[-1]
        curr_slow = slow_ema.iloc[-1]
        curr_trend = trend_ema.iloc[-1]

        atr_val = atr(df["high"], df["low"], close, self._atr_period).iloc[-1]
        current_price = close.iloc[-1]

        bullish_cross = prev_fast <= prev_slow and curr_fast > curr_slow
        bearish_cross = prev_fast >= prev_slow and curr_fast < curr_slow

        if not bullish_cross and not bearish_cross:
            state = self.get_state(symbol)
            if state == StrategyState.LONG and curr_fast < curr_slow:
                return Signal(
                    symbol=symbol, direction=SignalDirection.CLOSE_LONG,
                    confidence=0.7, strategy_name=self._name,
                )
            if state == StrategyState.SHORT and curr_fast > curr_slow:
                return Signal(
                    symbol=symbol, direction=SignalDirection.CLOSE_SHORT,
                    confidence=0.7, strategy_name=self._name,
                )
            return None

        adx_val, _, _ = adx(df["high"], df["low"], close)
        current_adx = adx_val.iloc[-1]
        if current_adx < self._adx_min:
            return None

        if bullish_cross and current_price < curr_trend:
            return None
        if bearish_cross and current_price > curr_trend:
            return None

        confidence = self._calculate_confidence(
            df, fast_ema, slow_ema, bullish_cross, current_adx,
        )

        if self._volume_confirm:
            vol_sma = df["volume"].rolling(self._volume_sma).mean().iloc[-1]
            if df["volume"].iloc[-1] < vol_sma:
                confidence *= 0.65

        if confidence < self._min_confidence:
            return None

        sl_distance = atr_val * self._atr_sl_mult
        tp_distance = atr_val * self._atr_tp_mult

        if bullish_cross:
            return Signal(
                symbol=symbol, direction=SignalDirection.LONG,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(current_price - sl_distance, 2))),
                take_profit=Decimal(str(round(current_price + tp_distance, 2))),
                metadata={
                    "fast_ema": curr_fast, "slow_ema": curr_slow,
                    "trend_ema": curr_trend, "adx": current_adx, "atr": atr_val,
                },
            )

        return Signal(
            symbol=symbol, direction=SignalDirection.SHORT,
            confidence=confidence, strategy_name=self._name,
            entry_price=Decimal(str(round(current_price, 2))),
            stop_loss=Decimal(str(round(current_price + sl_distance, 2))),
            take_profit=Decimal(str(round(current_price - tp_distance, 2))),
            metadata={
                "fast_ema": curr_fast, "slow_ema": curr_slow,
                "trend_ema": curr_trend, "adx": current_adx, "atr": atr_val,
            },
        )

    def _calculate_confidence(
        self,
        df: pd.DataFrame,
        fast: pd.Series,
        slow: pd.Series,
        is_bullish: bool,
        adx_value: float,
    ) -> float:
        spread = abs(fast.iloc[-1] - slow.iloc[-1]) / slow.iloc[-1]
        spread_score = min(spread * 100, 1.0)

        trend_bars = 0
        for i in range(-2, max(-10, -len(df)), -1):
            if is_bullish and fast.iloc[i] < slow.iloc[i]:
                trend_bars += 1
            elif not is_bullish and fast.iloc[i] > slow.iloc[i]:
                trend_bars += 1
            else:
                break

        trend_score = min(trend_bars / 5.0, 1.0)
        adx_score = min((adx_value - self._adx_min) / 30.0, 1.0)

        return 0.4 + 0.2 * spread_score + 0.2 * trend_score + 0.2 * adx_score
