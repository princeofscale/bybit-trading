import numpy as np
import pandas as pd
import ta


def rsi(close: pd.Series, window: int = 14, fillna: bool = True) -> pd.Series:
    return ta.momentum.rsi(close, window=window, fillna=fillna)


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
    smooth_window: int = 3,
    fillna: bool = True,
) -> tuple[pd.Series, pd.Series]:
    indicator = ta.momentum.StochasticOscillator(
        high, low, close, window=window, smooth_window=smooth_window, fillna=fillna,
    )
    return indicator.stoch(), indicator.stoch_signal()


def roc(close: pd.Series, window: int = 10, fillna: bool = True) -> pd.Series:
    return ta.momentum.roc(close, window=window, fillna=fillna)


def williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lbp: int = 14,
    fillna: bool = True,
) -> pd.Series:
    return ta.momentum.williams_r(high, low, close, lbp=lbp, fillna=fillna)


def cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
    constant: float = 0.015,
    fillna: bool = True,
) -> pd.Series:
    return ta.trend.cci(high, low, close, window=window, constant=constant, fillna=fillna)


def tsi(
    close: pd.Series,
    window_slow: int = 25,
    window_fast: int = 13,
    fillna: bool = True,
) -> pd.Series:
    return ta.momentum.tsi(close, window_slow=window_slow, window_fast=window_fast, fillna=fillna)


def awesome_oscillator(
    high: pd.Series,
    low: pd.Series,
    window1: int = 5,
    window2: int = 34,
    fillna: bool = True,
) -> pd.Series:
    return ta.momentum.awesome_oscillator(high, low, window1=window1, window2=window2, fillna=fillna)


def ultimate_oscillator(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window1: int = 7,
    window2: int = 14,
    window3: int = 28,
    fillna: bool = True,
) -> pd.Series:
    return ta.momentum.ultimate_oscillator(
        high, low, close, window1=window1, window2=window2, window3=window3, fillna=fillna,
    )


def momentum_score(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    rsi_window: int = 14,
    roc_window: int = 10,
) -> pd.Series:
    rsi_val = rsi(close, rsi_window)
    roc_val = roc(close, roc_window)
    stoch_k, _ = stochastic(high, low, close)

    rsi_norm = (rsi_val - 50) / 50
    roc_norm = roc_val / roc_val.rolling(roc_window).std().replace(0, 1)
    stoch_norm = (stoch_k - 50) / 50

    score = (rsi_norm * 0.4 + roc_norm * 0.3 + stoch_norm * 0.3)
    return score.fillna(0.0)
