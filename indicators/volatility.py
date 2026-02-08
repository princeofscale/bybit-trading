import numpy as np
import pandas as pd
import ta


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
    fillna: bool = True,
) -> pd.Series:
    return ta.volatility.average_true_range(high, low, close, window=window, fillna=fillna)


def bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
    fillna: bool = True,
) -> dict[str, pd.Series]:
    bb = ta.volatility.BollingerBands(close, window=window, window_dev=num_std, fillna=fillna)
    return {
        "upper": bb.bollinger_hband(),
        "middle": bb.bollinger_mavg(),
        "lower": bb.bollinger_lband(),
        "width": bb.bollinger_wband(),
        "pct_b": bb.bollinger_pband(),
    }


def keltner_channel(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
    atr_window: int = 10,
    fillna: bool = True,
) -> dict[str, pd.Series]:
    kc = ta.volatility.KeltnerChannel(
        high, low, close, window=window, window_atr=atr_window, fillna=fillna,
    )
    return {
        "upper": kc.keltner_channel_hband(),
        "middle": kc.keltner_channel_mband(),
        "lower": kc.keltner_channel_lband(),
    }


def donchian_channel(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
    fillna: bool = True,
) -> dict[str, pd.Series]:
    dc = ta.volatility.DonchianChannel(high, low, close, window=window, fillna=fillna)
    return {
        "upper": dc.donchian_channel_hband(),
        "middle": dc.donchian_channel_mband(),
        "lower": dc.donchian_channel_lband(),
        "width": dc.donchian_channel_wband(),
    }


def realized_volatility(
    close: pd.Series,
    window: int = 20,
    annualize: bool = True,
    periods_per_year: int = 365 * 24 * 4,
) -> pd.Series:
    log_returns = np.log(close / close.shift(1))
    rv = log_returns.rolling(window).std()
    if annualize:
        rv = rv * np.sqrt(periods_per_year)
    return rv.fillna(0.0)


def parkinson_volatility(
    high: pd.Series,
    low: pd.Series,
    window: int = 20,
    annualize: bool = True,
    periods_per_year: int = 365 * 24 * 4,
) -> pd.Series:
    log_hl = np.log(high / low) ** 2
    factor = 1.0 / (4.0 * np.log(2))
    pv = np.sqrt(factor * log_hl.rolling(window).mean())
    if annualize:
        pv = pv * np.sqrt(periods_per_year)
    return pv.fillna(0.0)


def garman_klass_volatility(
    open_price: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
    annualize: bool = True,
    periods_per_year: int = 365 * 24 * 4,
) -> pd.Series:
    log_hl = (np.log(high / low)) ** 2
    log_co = (np.log(close / open_price)) ** 2
    gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
    gkv = np.sqrt(gk.rolling(window).mean())
    if annualize:
        gkv = gkv * np.sqrt(periods_per_year)
    return gkv.fillna(0.0)


def volatility_regime(
    close: pd.Series,
    short_window: int = 10,
    long_window: int = 60,
) -> pd.Series:
    short_vol = realized_volatility(close, short_window, annualize=False)
    long_vol = realized_volatility(close, long_window, annualize=False)
    ratio = short_vol / long_vol.replace(0, np.nan)
    return ratio.fillna(1.0)


def squeeze_momentum(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    bb_window: int = 20,
    bb_std: float = 2.0,
    kc_window: int = 20,
    kc_atr: int = 10,
    kc_mult: float = 1.5,
    fillna: bool = True,
) -> tuple[pd.Series, pd.Series]:
    bb = ta.volatility.BollingerBands(close, window=bb_window, window_dev=bb_std, fillna=fillna)
    kc = ta.volatility.KeltnerChannel(high, low, close, window=kc_window, window_atr=kc_atr, fillna=fillna)

    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    kc_upper = kc.keltner_channel_hband() * kc_mult / 2
    kc_lower = kc.keltner_channel_lband() * kc_mult / 2

    squeeze_on = ((bb_lower > kc_lower) & (bb_upper < kc_upper)).astype(int)

    highest = high.rolling(bb_window).max()
    lowest = low.rolling(bb_window).min()
    mid = (highest + lowest) / 2
    sma_mid = close.rolling(bb_window).mean()
    momentum = close - (mid + sma_mid) / 2

    if fillna:
        squeeze_on = squeeze_on.fillna(0).astype(int)
        momentum = momentum.fillna(0.0)

    return squeeze_on, momentum
