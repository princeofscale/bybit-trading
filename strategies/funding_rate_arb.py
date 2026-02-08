from decimal import Decimal

import pandas as pd

from indicators.on_chain import funding_arb_signal, funding_rate_zscore
from strategies.base_strategy import BaseStrategy, Signal, SignalDirection, StrategyState


class FundingRateArbStrategy(BaseStrategy):
    def __init__(
        self,
        symbols: list[str],
        funding_threshold: float = 0.0003,
        extreme_threshold: float = 0.001,
        zscore_window: int = 30,
        zscore_entry: float = 2.0,
        zscore_exit: float = 0.5,
        min_confidence: float = 0.5,
    ) -> None:
        super().__init__("funding_rate_arb", symbols)
        self._threshold = funding_threshold
        self._extreme = extreme_threshold
        self._zscore_window = zscore_window
        self._zscore_entry = zscore_entry
        self._zscore_exit = zscore_exit
        self._min_confidence = min_confidence

    def min_candles_required(self) -> int:
        return self._zscore_window + 5

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        if "funding_rate" not in df.columns:
            return None
        if len(df) < self.min_candles_required():
            return None

        funding = df["funding_rate"]
        current_funding = funding.iloc[-1]
        current_price = df["close"].iloc[-1]

        zscore = funding_rate_zscore(funding, self._zscore_window)
        current_zscore = zscore.iloc[-1]

        state = self.get_state(symbol)

        if state == StrategyState.LONG and abs(current_zscore) < self._zscore_exit:
            return Signal(
                symbol=symbol, direction=SignalDirection.CLOSE_LONG,
                confidence=0.7, strategy_name=self._name,
            )
        if state == StrategyState.SHORT and abs(current_zscore) < self._zscore_exit:
            return Signal(
                symbol=symbol, direction=SignalDirection.CLOSE_SHORT,
                confidence=0.7, strategy_name=self._name,
            )

        if abs(current_zscore) < self._zscore_entry:
            return None

        confidence = self._calc_confidence(current_funding, current_zscore)
        if confidence < self._min_confidence:
            return None

        if current_funding > self._threshold:
            return Signal(
                symbol=symbol, direction=SignalDirection.SHORT,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                metadata={
                    "funding_rate": current_funding,
                    "zscore": current_zscore,
                    "annualized_yield": current_funding * 3 * 365,
                },
            )

        if current_funding < -self._threshold:
            return Signal(
                symbol=symbol, direction=SignalDirection.LONG,
                confidence=confidence, strategy_name=self._name,
                entry_price=Decimal(str(round(current_price, 2))),
                metadata={
                    "funding_rate": current_funding,
                    "zscore": current_zscore,
                    "annualized_yield": abs(current_funding) * 3 * 365,
                },
            )

        return None

    def _calc_confidence(self, funding: float, zscore: float) -> float:
        zscore_conf = min(abs(zscore) / 4.0, 1.0)
        funding_conf = min(abs(funding) / self._extreme, 1.0)
        return 0.5 * zscore_conf + 0.5 * funding_conf
