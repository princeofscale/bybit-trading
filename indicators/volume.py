import numpy as np
import pandas as pd
import ta


def obv(close: pd.Series, volume: pd.Series, fillna: bool = True) -> pd.Series:
    return ta.volume.on_balance_volume(close, volume, fillna=fillna)


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    window: int = 14,
    fillna: bool = True,
) -> pd.Series:
    return ta.volume.volume_weighted_average_price(
        high, low, close, volume, window=window, fillna=fillna,
    )


def mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    window: int = 14,
    fillna: bool = True,
) -> pd.Series:
    return ta.volume.money_flow_index(high, low, close, volume, window=window, fillna=fillna)


def accumulation_distribution(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    fillna: bool = True,
) -> pd.Series:
    return ta.volume.acc_dist_index(high, low, close, volume, fillna=fillna)


def chaikin_money_flow(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    window: int = 20,
    fillna: bool = True,
) -> pd.Series:
    return ta.volume.chaikin_money_flow(high, low, close, volume, window=window, fillna=fillna)


def force_index(
    close: pd.Series,
    volume: pd.Series,
    window: int = 13,
    fillna: bool = True,
) -> pd.Series:
    return ta.volume.force_index(close, volume, window=window, fillna=fillna)


def ease_of_movement(
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    window: int = 14,
    fillna: bool = True,
) -> pd.Series:
    return ta.volume.ease_of_movement(high, low, volume, window=window, fillna=fillna)


def volume_profile(
    close: pd.Series,
    volume: pd.Series,
    bins: int = 50,
) -> pd.DataFrame:
    price_min = close.min()
    price_max = close.max()
    bin_edges = np.linspace(price_min, price_max, bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    vol_at_price = np.zeros(bins)
    for i in range(bins):
        mask = (close >= bin_edges[i]) & (close < bin_edges[i + 1])
        vol_at_price[i] = volume[mask].sum()

    return pd.DataFrame({"price": bin_centers, "volume": vol_at_price})


def delta_volume(
    open_price: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    buy_vol = volume.where(close >= open_price, 0.0)
    sell_vol = volume.where(close < open_price, 0.0)
    return buy_vol - sell_vol


def cumulative_delta(
    open_price: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    return delta_volume(open_price, close, volume).cumsum()


def volume_ratio(
    volume: pd.Series,
    window: int = 20,
) -> pd.Series:
    avg_vol = volume.rolling(window).mean()
    ratio = volume / avg_vol.replace(0, np.nan)
    return ratio.fillna(0.0)


def volume_weighted_rsi(
    close: pd.Series,
    volume: pd.Series,
    window: int = 14,
) -> pd.Series:
    delta = close.diff()
    vol_delta = delta * volume
    gain = vol_delta.where(vol_delta > 0, 0.0).rolling(window).sum()
    loss = (-vol_delta.where(vol_delta < 0, 0.0)).rolling(window).sum()
    rs = gain / loss.replace(0, np.nan)
    vw_rsi = 100 - (100 / (1 + rs))
    return vw_rsi.fillna(50.0)
