from pydantic import BaseModel, Field

from data.models import MarketCategory


class TradingPairConfig(BaseModel):
    symbol: str
    ccxt_symbol: str
    category: MarketCategory
    enabled: bool = True
    max_leverage: int = 3
    min_position_size_usd: float = 10.0


DEFAULT_TRADING_PAIRS: list[TradingPairConfig] = [
    TradingPairConfig(
        symbol="BTCUSDT",
        ccxt_symbol="BTC/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="ETHUSDT",
        ccxt_symbol="ETH/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="SOLUSDT",
        ccxt_symbol="SOL/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="XRPUSDT",
        ccxt_symbol="XRP/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="DOGEUSDT",
        ccxt_symbol="DOGE/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="AVAXUSDT",
        ccxt_symbol="AVAX/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="ADAUSDT",
        ccxt_symbol="ADA/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="LINKUSDT",
        ccxt_symbol="LINK/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="DOTUSDT",
        ccxt_symbol="DOT/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="MATICUSDT",
        ccxt_symbol="MATIC/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="ARUSDT",
        ccxt_symbol="AR/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="SUIUSDT",
        ccxt_symbol="SUI/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="APTUSDT",
        ccxt_symbol="APT/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="OPUSDT",
        ccxt_symbol="OP/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
    TradingPairConfig(
        symbol="ARBUSDT",
        ccxt_symbol="ARB/USDT:USDT",
        category=MarketCategory.LINEAR,
    ),
]


def get_enabled_pairs() -> list[TradingPairConfig]:
    return [pair for pair in DEFAULT_TRADING_PAIRS if pair.enabled]


def get_symbols() -> list[str]:
    return [pair.symbol for pair in get_enabled_pairs()]


def get_ccxt_symbols() -> list[str]:
    return [pair.ccxt_symbol for pair in get_enabled_pairs()]
