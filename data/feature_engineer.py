import numpy as np
import pandas as pd
import structlog
import ta

logger = structlog.get_logger("feature_engineer")


class FeatureEngineer:
    def __init__(self, fillna: bool = True) -> None:
        self._fillna = fillna

    def add_trend_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        df["ema_9"] = ta.trend.ema_indicator(close, window=9, fillna=self._fillna)
        df["ema_21"] = ta.trend.ema_indicator(close, window=21, fillna=self._fillna)
        df["ema_50"] = ta.trend.ema_indicator(close, window=50, fillna=self._fillna)
        df["sma_20"] = ta.trend.sma_indicator(close, window=20, fillna=self._fillna)
        df["sma_200"] = ta.trend.sma_indicator(close, window=200, fillna=self._fillna)

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9, fillna=self._fillna)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_histogram"] = macd.macd_diff()

        adx = ta.trend.ADXIndicator(high, low, close, window=14, fillna=self._fillna)
        df["adx"] = adx.adx()
        df["adx_pos"] = adx.adx_pos()
        df["adx_neg"] = adx.adx_neg()

        return df

    def add_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        df["rsi_14"] = ta.momentum.rsi(close, window=14, fillna=self._fillna)
        df["rsi_7"] = ta.momentum.rsi(close, window=7, fillna=self._fillna)

        stoch = ta.momentum.StochasticOscillator(
            high, low, close, window=14, smooth_window=3, fillna=self._fillna,
        )
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()

        df["roc_10"] = ta.momentum.roc(close, window=10, fillna=self._fillna)
        df["williams_r"] = ta.momentum.williams_r(
            high, low, close, lbp=14, fillna=self._fillna,
        )

        return df

    def add_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2, fillna=self._fillna)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_width"] = bb.bollinger_wband()
        df["bb_pct"] = bb.bollinger_pband()

        df["atr_14"] = ta.volatility.average_true_range(
            high, low, close, window=14, fillna=self._fillna,
        )
        df["atr_7"] = ta.volatility.average_true_range(
            high, low, close, window=7, fillna=self._fillna,
        )

        kc = ta.volatility.KeltnerChannel(
            high, low, close, window=20, window_atr=10, fillna=self._fillna,
        )
        df["kc_upper"] = kc.keltner_channel_hband()
        df["kc_lower"] = kc.keltner_channel_lband()

        return df

    def add_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        df["obv"] = ta.volume.on_balance_volume(close, volume, fillna=self._fillna)
        df["vwap"] = ta.volume.volume_weighted_average_price(
            high, low, close, volume, window=14, fillna=self._fillna,
        )
        df["mfi_14"] = ta.volume.money_flow_index(
            high, low, close, volume, window=14, fillna=self._fillna,
        )
        df["adi"] = ta.volume.acc_dist_index(high, low, close, volume, fillna=self._fillna)

        df["volume_sma_20"] = volume.rolling(window=20).mean()
        df["volume_ratio"] = volume / df["volume_sma_20"]

        if self._fillna:
            df["volume_sma_20"] = df["volume_sma_20"].fillna(0.0)
            df["volume_ratio"] = df["volume_ratio"].fillna(0.0)

        return df

    def add_custom_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["price_range"] = (df["high"] - df["low"]) / df["close"]
        df["body_ratio"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"]).replace(0, np.nan)
        df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["close"]
        df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["close"]

        df["returns_1"] = df["close"].pct_change(1)
        df["returns_5"] = df["close"].pct_change(5)
        df["returns_10"] = df["close"].pct_change(10)

        df["volatility_10"] = df["close"].pct_change().rolling(10).std()
        df["volatility_20"] = df["close"].pct_change().rolling(20).std()

        df["high_low_ratio"] = df["high"] / df["low"]
        df["close_to_ema9"] = df["close"] / df.get("ema_9", df["close"]) - 1

        if self._fillna:
            df = df.fillna(0.0)

        return df

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.add_trend_indicators(df)
        df = self.add_momentum_indicators(df)
        df = self.add_volatility_indicators(df)
        df = self.add_volume_indicators(df)
        df = self.add_custom_features(df)
        return df

    def get_feature_columns(self) -> list[str]:
        return [
            "ema_9", "ema_21", "ema_50", "sma_20", "sma_200",
            "macd", "macd_signal", "macd_histogram",
            "adx", "adx_pos", "adx_neg",
            "rsi_14", "rsi_7",
            "stoch_k", "stoch_d",
            "roc_10", "williams_r",
            "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
            "atr_14", "atr_7",
            "kc_upper", "kc_lower",
            "obv", "vwap", "mfi_14", "adi",
            "volume_sma_20", "volume_ratio",
            "price_range", "body_ratio", "upper_shadow", "lower_shadow",
            "returns_1", "returns_5", "returns_10",
            "volatility_10", "volatility_20",
            "high_low_ratio", "close_to_ema9",
        ]
