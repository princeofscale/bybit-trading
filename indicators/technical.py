import numpy as np
import pandas as pd
import ta


def ema(series: pd.Series, window: int = 20, fillna: bool = True) -> pd.Series:
    return ta.trend.ema_indicator(series, window=window, fillna=fillna)


def sma(series: pd.Series, window: int = 20, fillna: bool = True) -> pd.Series:
    return ta.trend.sma_indicator(series, window=window, fillna=fillna)


def wma(series: pd.Series, window: int = 20) -> pd.Series:
    weights = np.arange(1, window + 1, dtype=float)
    return series.rolling(window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)


def hull_ma(series: pd.Series, window: int = 20, fillna: bool = True) -> pd.Series:
    half = int(window / 2)
    sqrt_window = int(np.sqrt(window))
    wma_half = wma(series, half)
    wma_full = wma(series, window)
    diff = 2 * wma_half - wma_full
    result = wma(diff, sqrt_window)
    if fillna:
        result = result.bfill()
    return result


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    fillna: bool = True,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    indicator = ta.trend.MACD(close, window_slow=slow, window_fast=fast, window_sign=signal, fillna=fillna)
    return indicator.macd(), indicator.macd_signal(), indicator.macd_diff()


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
    fillna: bool = True,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    indicator = ta.trend.ADXIndicator(high, low, close, window=window, fillna=fillna)
    return indicator.adx(), indicator.adx_pos(), indicator.adx_neg()


def ichimoku(
    high: pd.Series,
    low: pd.Series,
    window1: int = 9,
    window2: int = 26,
    window3: int = 52,
    fillna: bool = True,
) -> dict[str, pd.Series]:
    indicator = ta.trend.IchimokuIndicator(
        high, low, window1=window1, window2=window2, window3=window3, fillna=fillna,
    )
    return {
        "tenkan_sen": indicator.ichimoku_conversion_line(),
        "kijun_sen": indicator.ichimoku_base_line(),
        "senkou_a": indicator.ichimoku_a(),
        "senkou_b": indicator.ichimoku_b(),
    }


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_window: int = 10,
    multiplier: float = 3.0,
    fillna: bool = True,
) -> tuple[pd.Series, pd.Series]:
    atr_vals = ta.volatility.average_true_range(high, low, close, window=atr_window, fillna=fillna)
    hl2 = (high + low) / 2
    upper = hl2 + multiplier * atr_vals
    lower = hl2 - multiplier * atr_vals

    direction = pd.Series(1, index=close.index, dtype=int)
    st = pd.Series(np.nan, index=close.index)

    for i in range(1, len(close)):
        if close.iloc[i] > upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        if direction.iloc[i] == 1:
            st.iloc[i] = lower.iloc[i]
        else:
            st.iloc[i] = upper.iloc[i]

    if fillna:
        st = st.bfill()
        direction = direction.fillna(1)

    return st, direction


def pivot_points(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> dict[str, pd.Series]:
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)
    return {"pivot": pivot, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3}
