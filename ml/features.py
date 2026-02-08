import numpy as np
import pandas as pd


FEATURE_GROUPS = {
    "trend": [
        "ema_9", "ema_21", "ema_50", "sma_20", "sma_200",
        "ema_9_slope", "ema_21_slope", "price_vs_ema50",
    ],
    "momentum": [
        "rsi_14", "rsi_7", "roc_10", "roc_20",
        "stoch_k", "stoch_d", "macd_hist",
    ],
    "volatility": [
        "atr_14", "bb_width", "bb_pct", "realized_vol_20",
        "high_low_range", "atr_ratio",
    ],
    "volume": [
        "volume_sma_ratio", "obv_slope", "mfi_14",
        "volume_change", "dollar_volume",
    ],
    "price_action": [
        "body_ratio", "upper_shadow", "lower_shadow",
        "return_1", "return_3", "return_5", "return_10",
    ],
}


def get_all_feature_names() -> list[str]:
    names: list[str] = []
    for group in FEATURE_GROUPS.values():
        names.extend(group)
    return names


class MLFeatureEngineer:
    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out = self._add_trend_features(out)
        out = self._add_momentum_features(out)
        out = self._add_volatility_features(out)
        out = self._add_volume_features(out)
        out = self._add_price_action_features(out)
        return out

    def _add_trend_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["sma_20"] = df["close"].rolling(20).mean()
        df["sma_200"] = df["close"].rolling(200).mean()
        df["ema_9_slope"] = df["ema_9"].pct_change(3)
        df["ema_21_slope"] = df["ema_21"].pct_change(5)
        df["price_vs_ema50"] = (df["close"] - df["ema_50"]) / df["ema_50"]
        return df

    def _add_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        gain7 = delta.clip(lower=0).rolling(7).mean()
        loss7 = (-delta.clip(upper=0)).rolling(7).mean()
        rs7 = gain7 / loss7.replace(0, np.nan)
        df["rsi_7"] = 100 - (100 / (1 + rs7))

        df["roc_10"] = df["close"].pct_change(10)
        df["roc_20"] = df["close"].pct_change(20)

        low14 = df["low"].rolling(14).min()
        high14 = df["high"].rolling(14).max()
        denom = (high14 - low14).replace(0, np.nan)
        df["stoch_k"] = 100 * (df["close"] - low14) / denom
        df["stoch_d"] = df["stoch_k"].rolling(3).mean()

        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df["macd_hist"] = macd - signal
        return df

    def _add_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(14).mean()

        sma20 = df["close"].rolling(20).mean()
        std20 = df["close"].rolling(20).std()
        upper = sma20 + 2 * std20
        lower = sma20 - 2 * std20
        df["bb_width"] = (upper - lower) / sma20
        denom = (upper - lower).replace(0, np.nan)
        df["bb_pct"] = (df["close"] - lower) / denom

        df["realized_vol_20"] = df["close"].pct_change().rolling(20).std()
        df["high_low_range"] = (df["high"] - df["low"]) / df["close"]
        atr7 = tr.rolling(7).mean()
        df["atr_ratio"] = atr7 / df["atr_14"].replace(0, np.nan)
        return df

    def _add_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        vol_sma = df["volume"].rolling(20).mean()
        df["volume_sma_ratio"] = df["volume"] / vol_sma.replace(0, np.nan)
        obv = (np.sign(df["close"].diff()) * df["volume"]).cumsum()
        df["obv_slope"] = obv.pct_change(5)

        typical = (df["high"] + df["low"] + df["close"]) / 3
        raw_mf = typical * df["volume"]
        pos_mf = raw_mf.where(typical > typical.shift(), 0).rolling(14).sum()
        neg_mf = raw_mf.where(typical < typical.shift(), 0).rolling(14).sum()
        mfr = pos_mf / neg_mf.replace(0, np.nan)
        df["mfi_14"] = 100 - (100 / (1 + mfr))

        df["volume_change"] = df["volume"].pct_change()
        df["dollar_volume"] = df["close"] * df["volume"]
        return df

    def _add_price_action_features(self, df: pd.DataFrame) -> pd.DataFrame:
        body = (df["close"] - df["open"]).abs()
        hl = (df["high"] - df["low"]).replace(0, np.nan)
        df["body_ratio"] = body / hl
        df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / hl
        df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / hl

        for n in [1, 3, 5, 10]:
            df[f"return_{n}"] = df["close"].pct_change(n)
        return df

    def clean_features(self, df: pd.DataFrame) -> pd.DataFrame:
        feature_cols = get_all_feature_names()
        available = [c for c in feature_cols if c in df.columns]
        out = df[available].copy()
        out = out.replace([np.inf, -np.inf], np.nan)
        out = out.ffill().bfill().fillna(0)
        return out
