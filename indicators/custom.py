import numpy as np
import pandas as pd


def orderbook_imbalance(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    depth: int = 10,
) -> float:
    bid_vol = sum(qty for _, qty in bids[:depth])
    ask_vol = sum(qty for _, qty in asks[:depth])
    total = bid_vol + ask_vol
    if total == 0:
        return 0.0
    return (bid_vol - ask_vol) / total


def weighted_orderbook_imbalance(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    mid_price: float,
    depth: int = 10,
) -> float:
    if mid_price <= 0:
        return 0.0

    bid_weighted = sum(
        qty * (1 - abs(price - mid_price) / mid_price)
        for price, qty in bids[:depth]
    )
    ask_weighted = sum(
        qty * (1 - abs(price - mid_price) / mid_price)
        for price, qty in asks[:depth]
    )
    total = bid_weighted + ask_weighted
    if total == 0:
        return 0.0
    return (bid_weighted - ask_weighted) / total


def bid_ask_spread(best_bid: float, best_ask: float) -> float:
    if best_bid <= 0 or best_ask <= 0:
        return 0.0
    mid = (best_bid + best_ask) / 2
    return (best_ask - best_bid) / mid


def trade_flow_imbalance(
    prices: pd.Series,
    volumes: pd.Series,
    window: int = 20,
) -> pd.Series:
    direction = np.sign(prices.diff())
    buy_vol = (volumes * direction.clip(lower=0)).rolling(window).sum()
    sell_vol = (volumes * (-direction.clip(upper=0))).rolling(window).sum()
    total = buy_vol + sell_vol
    imbalance = (buy_vol - sell_vol) / total.replace(0, np.nan)
    return imbalance.fillna(0.0)


def price_momentum_divergence(
    close: pd.Series,
    rsi: pd.Series,
    window: int = 14,
) -> pd.Series:
    price_slope = close.diff(window) / close.shift(window)
    rsi_slope = rsi.diff(window)
    price_up = price_slope > 0
    rsi_down = rsi_slope < 0
    price_down = price_slope < 0
    rsi_up = rsi_slope > 0

    divergence = pd.Series(0, index=close.index)
    divergence = divergence.where(~(price_up & rsi_down), -1)
    divergence = divergence.where(~(price_down & rsi_up), 1)
    return divergence


def support_resistance_levels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
    num_levels: int = 3,
) -> dict[str, list[float]]:
    recent_high = high.tail(window)
    recent_low = low.tail(window)
    recent_close = close.tail(window)

    all_prices = pd.concat([recent_high, recent_low, recent_close])
    bins = np.linspace(all_prices.min(), all_prices.max(), 50)
    counts, edges = np.histogram(all_prices, bins=bins)

    top_indices = np.argsort(counts)[-num_levels * 2:]
    levels = sorted((edges[i] + edges[i + 1]) / 2 for i in top_indices)

    current = close.iloc[-1]
    resistance = [l for l in levels if l > current][:num_levels]
    support = [l for l in levels if l <= current][-num_levels:]

    return {"support": support, "resistance": resistance}


def market_regime(
    close: pd.Series,
    adx: pd.Series,
    atr: pd.Series,
    adx_threshold: float = 25.0,
    vol_window: int = 20,
) -> pd.Series:
    avg_atr = atr.rolling(vol_window).mean()
    high_vol = atr > avg_atr

    trending = adx > adx_threshold
    regime = pd.Series("low_vol_range", index=close.index)
    regime = regime.where(~(trending & high_vol), "high_vol_trend")
    regime = regime.where(~(trending & ~high_vol), "low_vol_trend")
    regime = regime.where(~(~trending & high_vol), "high_vol_range")
    return regime


def heikin_ashi(
    open_price: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> dict[str, pd.Series]:
    ha_close = (open_price + high + low + close) / 4
    ha_open = pd.Series(np.nan, index=open_price.index)
    ha_open.iloc[0] = (open_price.iloc[0] + close.iloc[0]) / 2

    for i in range(1, len(ha_open)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2

    ha_high = pd.concat([high, ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([low, ha_open, ha_close], axis=1).min(axis=1)

    return {"open": ha_open, "high": ha_high, "low": ha_low, "close": ha_close}
