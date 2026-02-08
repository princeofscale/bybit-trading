import numpy as np
import pandas as pd


def funding_rate_zscore(
    funding_rates: pd.Series,
    window: int = 30,
) -> pd.Series:
    mean = funding_rates.rolling(window).mean()
    std = funding_rates.rolling(window).std()
    zscore = (funding_rates - mean) / std.replace(0, np.nan)
    return zscore.fillna(0.0)


def open_interest_change(
    open_interest: pd.Series,
    window: int = 1,
) -> pd.Series:
    return open_interest.pct_change(window).fillna(0.0)


def open_interest_to_volume(
    open_interest: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    ratio = open_interest / volume.replace(0, np.nan)
    return ratio.fillna(0.0)


def long_short_ratio_signal(
    long_short_ratio: pd.Series,
    overbought: float = 2.0,
    oversold: float = 0.5,
) -> pd.Series:
    signal = pd.Series(0, index=long_short_ratio.index)
    signal = signal.where(long_short_ratio <= overbought, -1)
    signal = signal.where(long_short_ratio >= oversold, 1)
    return signal


def liquidation_intensity(
    liquidation_volume: pd.Series,
    total_volume: pd.Series,
    window: int = 24,
) -> pd.Series:
    ratio = liquidation_volume / total_volume.replace(0, np.nan)
    intensity = ratio.rolling(window).mean()
    return intensity.fillna(0.0)


def funding_arb_signal(
    funding_rate: pd.Series,
    threshold: float = 0.0003,
    extreme_threshold: float = 0.001,
) -> pd.Series:
    signal = pd.Series(0.0, index=funding_rate.index)

    long_signal = funding_rate < -threshold
    short_signal = funding_rate > threshold
    extreme_long = funding_rate < -extreme_threshold
    extreme_short = funding_rate > extreme_threshold

    signal = signal.where(~long_signal, 0.5)
    signal = signal.where(~extreme_long, 1.0)
    signal = signal.where(~short_signal, -0.5)
    signal = signal.where(~extreme_short, -1.0)

    return signal


def whale_activity_score(
    volume: pd.Series,
    avg_window: int = 50,
    spike_threshold: float = 3.0,
) -> pd.Series:
    avg_vol = volume.rolling(avg_window).mean()
    std_vol = volume.rolling(avg_window).std()
    zscore = (volume - avg_vol) / std_vol.replace(0, np.nan)
    score = zscore.clip(lower=0) / spike_threshold
    return score.clip(upper=1.0).fillna(0.0)
