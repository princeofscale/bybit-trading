from decimal import Decimal

import pytest

from data.cache import CandleBuffer, DataCache, LRUCache, TickerCache
from exchange.models import Candle, Ticker


class TestLRUCache:
    def test_set_and_get(self) -> None:
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self) -> None:
        cache = LRUCache()
        assert cache.get("nonexistent") is None

    def test_eviction_on_max_size(self) -> None:
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.size == 3

    def test_access_promotes_item(self) -> None:
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.get("a")
        cache.set("d", 4)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_update_existing_key(self) -> None:
        cache = LRUCache()
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"
        assert cache.size == 1

    def test_delete(self) -> None:
        cache = LRUCache()
        cache.set("key", "value")
        cache.delete("key")
        assert cache.get("key") is None
        assert cache.size == 0

    def test_delete_nonexistent(self) -> None:
        cache = LRUCache()
        cache.delete("missing")
        assert cache.size == 0

    def test_clear(self) -> None:
        cache = LRUCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0


def _make_candle(symbol: str = "BTC/USDT:USDT", tf: str = "15m", open_time: int = 1000, close: str = "100") -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=tf,
        open_time=open_time,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("10"),
    )


class TestCandleBuffer:
    def test_append_and_get(self) -> None:
        buf = CandleBuffer()
        c = _make_candle(open_time=1000)
        buf.append(c)
        result = buf.get_candles("BTC/USDT:USDT", "15m")
        assert len(result) == 1
        assert result[0].open_time == 1000

    def test_append_updates_same_open_time(self) -> None:
        buf = CandleBuffer()
        buf.append(_make_candle(open_time=1000, close="100"))
        buf.append(_make_candle(open_time=1000, close="105"))
        result = buf.get_candles("BTC/USDT:USDT", "15m")
        assert len(result) == 1
        assert result[0].close == Decimal("105")

    def test_get_candles_with_count(self) -> None:
        buf = CandleBuffer()
        for i in range(10):
            buf.append(_make_candle(open_time=i * 1000))
        result = buf.get_candles("BTC/USDT:USDT", "15m", count=3)
        assert len(result) == 3
        assert result[0].open_time == 7000

    def test_get_latest(self) -> None:
        buf = CandleBuffer()
        buf.append(_make_candle(open_time=1000))
        buf.append(_make_candle(open_time=2000))
        latest = buf.get_latest("BTC/USDT:USDT", "15m")
        assert latest is not None
        assert latest.open_time == 2000

    def test_get_latest_empty(self) -> None:
        buf = CandleBuffer()
        assert buf.get_latest("BTC/USDT:USDT", "15m") is None

    def test_max_candles_eviction(self) -> None:
        buf = CandleBuffer(max_candles_per_key=5)
        for i in range(10):
            buf.append(_make_candle(open_time=i * 1000))
        result = buf.get_candles("BTC/USDT:USDT", "15m")
        assert len(result) == 5
        assert result[0].open_time == 5000

    def test_load_initial(self) -> None:
        buf = CandleBuffer(max_candles_per_key=3)
        candles = [_make_candle(open_time=i * 1000) for i in range(5)]
        buf.load_initial("BTC/USDT:USDT", "15m", candles)
        result = buf.get_candles("BTC/USDT:USDT", "15m")
        assert len(result) == 3
        assert result[0].open_time == 2000

    def test_buffer_stats(self) -> None:
        buf = CandleBuffer()
        for i in range(3):
            buf.append(_make_candle(open_time=i * 1000))
        buf.append(_make_candle(symbol="ETH/USDT:USDT", open_time=1000))
        stats = buf.buffer_stats
        assert stats["BTC/USDT:USDT:15m"] == 3
        assert stats["ETH/USDT:USDT:15m"] == 1

    def test_different_timeframes(self) -> None:
        buf = CandleBuffer()
        buf.append(_make_candle(tf="1m", open_time=1000))
        buf.append(_make_candle(tf="15m", open_time=1000))
        assert len(buf.get_candles("BTC/USDT:USDT", "1m")) == 1
        assert len(buf.get_candles("BTC/USDT:USDT", "15m")) == 1


def _make_ticker(symbol: str = "BTC/USDT:USDT", funding: str = "0.0001") -> Ticker:
    return Ticker(
        symbol=symbol,
        last_price=Decimal("30000"),
        bid_price=Decimal("29999"),
        ask_price=Decimal("30001"),
        high_24h=Decimal("31000"),
        low_24h=Decimal("29000"),
        volume_24h=Decimal("1000"),
        turnover_24h=Decimal("30000000"),
        funding_rate=Decimal(funding),
    )


class TestTickerCache:
    def test_update_and_get(self) -> None:
        tc = TickerCache()
        tc.update(_make_ticker())
        ticker = tc.get("BTC/USDT:USDT")
        assert ticker is not None
        assert ticker.last_price == Decimal("30000")

    def test_get_missing(self) -> None:
        tc = TickerCache()
        assert tc.get("MISSING") is None

    def test_get_all(self) -> None:
        tc = TickerCache()
        tc.update(_make_ticker("BTC/USDT:USDT"))
        tc.update(_make_ticker("ETH/USDT:USDT"))
        all_tickers = tc.get_all()
        assert len(all_tickers) == 2

    def test_get_funding_rate(self) -> None:
        tc = TickerCache()
        tc.update(_make_ticker(funding="0.0003"))
        assert tc.get_funding_rate("BTC/USDT:USDT") == Decimal("0.0003")

    def test_get_funding_rate_missing(self) -> None:
        tc = TickerCache()
        assert tc.get_funding_rate("MISSING") == Decimal("0")

    def test_update_overwrites(self) -> None:
        tc = TickerCache()
        tc.update(_make_ticker(funding="0.0001"))
        tc.update(_make_ticker(funding="0.0005"))
        assert tc.get_funding_rate("BTC/USDT:USDT") == Decimal("0.0005")


class TestDataCache:
    def test_composite_cache(self) -> None:
        dc = DataCache(max_candles_per_buffer=100)
        dc.candles.append(_make_candle(open_time=1000))
        dc.tickers.update(_make_ticker())
        dc.lru.set("key", "value")

        assert dc.candles.get_latest("BTC/USDT:USDT", "15m") is not None
        assert dc.tickers.get("BTC/USDT:USDT") is not None
        assert dc.lru.get("key") == "value"
