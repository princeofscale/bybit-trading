import numpy as np
import pandas as pd


def rolling_correlation(
    series_a: pd.Series,
    series_b: pd.Series,
    window: int = 30,
) -> pd.Series:
    return series_a.rolling(window).corr(series_b).fillna(0.0)


def correlation_matrix(
    price_dict: dict[str, pd.Series],
    window: int = 30,
) -> pd.DataFrame:
    df = pd.DataFrame(price_dict)
    returns = df.pct_change()
    return returns.rolling(window).corr().iloc[-len(price_dict):]


def beta(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    window: int = 30,
) -> pd.Series:
    cov = asset_returns.rolling(window).cov(benchmark_returns)
    var = benchmark_returns.rolling(window).var()
    return (cov / var.replace(0, np.nan)).fillna(0.0)


def cointegration_spread(
    series_a: pd.Series,
    series_b: pd.Series,
    window: int = 60,
) -> tuple[pd.Series, pd.Series]:
    ratio = series_a / series_b.replace(0, np.nan)
    mean = ratio.rolling(window).mean()
    std = ratio.rolling(window).std()
    zscore = (ratio - mean) / std.replace(0, np.nan)
    return ratio.fillna(0.0), zscore.fillna(0.0)


def cross_asset_momentum(
    price_dict: dict[str, pd.Series],
    window: int = 20,
) -> pd.DataFrame:
    returns = {sym: p.pct_change(window).fillna(0.0) for sym, p in price_dict.items()}
    return pd.DataFrame(returns)


def pair_distance(
    series_a: pd.Series,
    series_b: pd.Series,
    window: int = 60,
) -> pd.Series:
    norm_a = series_a / series_a.rolling(window).mean()
    norm_b = series_b / series_b.rolling(window).mean()
    return (norm_a - norm_b).fillna(0.0)
