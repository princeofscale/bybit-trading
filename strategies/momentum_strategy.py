from decimal import Decimal

import pandas as pd

from indicators.momentum import momentum_score, roc, rsi
from indicators.technical import adx, ema
from indicators.volatility import atr
from indicators.volume import volume_ratio
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class MomentumStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        roc_period: int = 10,
        rsi_period: int = 14,
        volume_sma_period: int = 20,
        atr_period: int = 14,
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.5,
        momentum_threshold: float = 0.35,
        volume_threshold: float = 1.3,
        adx_min_threshold: float = 20.0,
        ema_fast: int = 21,
        ema_slow: int = 50,
        min_confidence: float = 0.55,
    ) -> None:
        super().__init__("momentum", symbols)
        self._roc_period = roc_period
        self._rsi_period = rsi_period
        self._vol_sma = volume_sma_period
        self._atr_period = atr_period
        self._atr_sl_mult = atr_sl_multiplier
        self._atr_tp_mult = atr_tp_multiplier
        self._mom_threshold = momentum_threshold
        self._vol_threshold = volume_threshold
        self._adx_min = adx_min_threshold
        self._ema_fast = ema_fast
        self._ema_slow = ema_slow
        self._min_confidence = min_confidence

    def min_candles_required(self) -> int:
        return max(self._roc_period, self._rsi_period, self._vol_sma, self._ema_slow) + 15

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_candles_required():
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]

        score = momentum_score(close, high, low, self._rsi_period, self._roc_period)
        rsi_val = rsi(close, self._rsi_period).iloc[-1]
        vol_r = volume_ratio(df["volume"], self._vol_sma).iloc[-1]
        atr_val = atr(high, low, close, self._atr_period).iloc[-1]

        current_score = score.iloc[-1]
        current_price = close.iloc[-1]
        state = self.get_state(symbol)

        if state == StrategyState.LONG and current_score < 0:
            return Signal(
                symbol=symbol, direction=SignalDirection.CLOSE_LONG,
                confidence=0.65, strategy_name=self._name,
            )
        if state == StrategyState.SHORT and current_score > 0:
            return Signal(
                symbol=symbol, direction=SignalDirection.CLOSE_SHORT,
                confidence=0.65, strategy_name=self._name,
            )

        volume_confirmed = vol_r >= self._vol_threshold
        strong_momentum = abs(current_score) > self._mom_threshold

        if not (strong_momentum and volume_confirmed):
            return None

        adx_val, _, _ = adx(high, low, close)
        current_adx = adx_val.iloc[-1]
        if current_adx < self._adx_min:
            return None

        fast_ema_val = ema(close, self._ema_fast).iloc[-1]
        slow_ema_val = ema(close, self._ema_slow).iloc[-1]

        if current_score > 0 and fast_ema_val < slow_ema_val:
            return None
        if current_score < 0 and fast_ema_val > slow_ema_val:
            return None

        prev_score = score.iloc[-2]
        if current_score > 0 and current_score < prev_score:
            return None
        if current_score < 0 and current_score > prev_score:
            return None

        confidence = self._calc_confidence(current_score, rsi_val, vol_r, current_adx)
        if confidence < self._min_confidence:
            return None

        sl_dist = atr_val * self._atr_sl_mult
        tp_dist = atr_val * self._atr_tp_mult

        if current_score > 0:
            return Signal(
                symbol=symbol, direction=SignalDirection.LONG,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                stop_loss=Decimal(str(round(current_price - sl_dist, 2))),
                take_profit=Decimal(str(round(current_price + tp_dist, 2))),
                metadata={
                    "score": current_score, "rsi": rsi_val,
                    "vol_ratio": vol_r, "adx": current_adx,
                },
            )

        return Signal(
            symbol=symbol, direction=SignalDirection.SHORT,
            confidence=confidence, strategy_name=self._name,
            entry_price=Decimal(str(round(current_price, 2))),
            stop_loss=Decimal(str(round(current_price + sl_dist, 2))),
            take_profit=Decimal(str(round(current_price - tp_dist, 2))),
            metadata={
                "score": current_score, "rsi": rsi_val,
                "vol_ratio": vol_r, "adx": current_adx,
            },
        )

    def _calc_confidence(
        self, score: float, rsi_val: float, vol_ratio: float, adx_value: float,
    ) -> float:
        score_conf = min(abs(score), 1.0)
        rsi_conf = abs(rsi_val - 50) / 50
        vol_conf = min(vol_ratio / 3.0, 1.0)
        adx_conf = min((adx_value - self._adx_min) / 30.0, 1.0)
        return 0.3 * score_conf + 0.2 * rsi_conf + 0.25 * vol_conf + 0.25 * adx_conf
