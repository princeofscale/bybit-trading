from decimal import Decimal
from time import sleep

import pytest

from monitoring.metrics import (
    Counter,
    Gauge,
    Histogram,
    LatencyTracker,
    MetricType,
    MetricsRegistry,
)


class TestCounter:
    def test_initial_value_zero(self) -> None:
        c = Counter("orders_total")
        assert c.value == Decimal("0")

    def test_increment_default(self) -> None:
        c = Counter("orders_total")
        c.increment()
        assert c.value == Decimal("1")

    def test_increment_custom(self) -> None:
        c = Counter("volume_usd")
        c.increment(Decimal("1500.50"))
        assert c.value == Decimal("1500.50")

    def test_multiple_increments(self) -> None:
        c = Counter("trades")
        c.increment()
        c.increment()
        c.increment(Decimal("3"))
        assert c.value == Decimal("5")

    def test_reset(self) -> None:
        c = Counter("errors")
        c.increment(Decimal("10"))
        c.reset()
        assert c.value == Decimal("0")

    def test_to_point(self) -> None:
        c = Counter("fills", tags={"symbol": "BTCUSDT"})
        c.increment(Decimal("5"))
        point = c.to_point()
        assert point.name == "fills"
        assert point.value == Decimal("5")
        assert point.metric_type == MetricType.COUNTER
        assert point.tags["symbol"] == "BTCUSDT"

    def test_name_property(self) -> None:
        c = Counter("test_counter")
        assert c.name == "test_counter"


class TestGauge:
    def test_initial_zero(self) -> None:
        g = Gauge("equity")
        assert g.value == Decimal("0")

    def test_set_value(self) -> None:
        g = Gauge("equity")
        g.set(Decimal("50000"))
        assert g.value == Decimal("50000")

    def test_set_overrides(self) -> None:
        g = Gauge("unrealized_pnl")
        g.set(Decimal("100"))
        g.set(Decimal("-50"))
        assert g.value == Decimal("-50")

    def test_to_point(self) -> None:
        g = Gauge("balance")
        g.set(Decimal("10000"))
        point = g.to_point()
        assert point.metric_type == MetricType.GAUGE
        assert point.value == Decimal("10000")


class TestHistogram:
    def test_empty(self) -> None:
        h = Histogram("latency_ms")
        assert h.count == 0
        assert h.mean == Decimal("0")
        assert h.p50 == Decimal("0")

    def test_single_observe(self) -> None:
        h = Histogram("latency_ms")
        h.observe(Decimal("15.5"))
        assert h.count == 1
        assert h.mean == Decimal("15.5")

    def test_mean_calculation(self) -> None:
        h = Histogram("latency_ms")
        h.observe(Decimal("10"))
        h.observe(Decimal("20"))
        h.observe(Decimal("30"))
        assert h.mean == Decimal("20")

    def test_percentiles(self) -> None:
        h = Histogram("response_time")
        for i in range(1, 101):
            h.observe(Decimal(str(i)))
        assert h.p50 == Decimal("50")
        assert h.p95 == Decimal("95")
        assert h.p99 == Decimal("99")

    def test_reset_clears(self) -> None:
        h = Histogram("latency")
        h.observe(Decimal("10"))
        h.observe(Decimal("20"))
        h.reset()
        assert h.count == 0
        assert h.mean == Decimal("0")


class TestLatencyTracker:
    def test_records_latency(self) -> None:
        h = Histogram("api_latency")
        tracker = LatencyTracker(h)
        tracker.start()
        sleep(0.01)
        tracker.stop()
        assert h.count == 1
        assert h.mean > Decimal("0")

    def test_stop_without_start_noop(self) -> None:
        h = Histogram("api_latency")
        tracker = LatencyTracker(h)
        tracker.stop()
        assert h.count == 0

    def test_histogram_property(self) -> None:
        h = Histogram("test")
        tracker = LatencyTracker(h)
        assert tracker.histogram is h


class TestMetricsRegistry:
    def test_creates_counter(self) -> None:
        reg = MetricsRegistry()
        c = reg.counter("orders")
        c.increment()
        assert reg.counter("orders").value == Decimal("1")

    def test_creates_gauge(self) -> None:
        reg = MetricsRegistry()
        g = reg.gauge("equity")
        g.set(Decimal("50000"))
        assert reg.gauge("equity").value == Decimal("50000")

    def test_creates_histogram(self) -> None:
        reg = MetricsRegistry()
        h = reg.histogram("latency")
        h.observe(Decimal("10"))
        assert reg.histogram("latency").count == 1

    def test_same_name_returns_same_instance(self) -> None:
        reg = MetricsRegistry()
        c1 = reg.counter("x")
        c2 = reg.counter("x")
        assert c1 is c2

    def test_latency_tracker(self) -> None:
        reg = MetricsRegistry()
        tracker = reg.latency_tracker("api_call")
        assert "api_call" in reg.histogram_names

    def test_get_all_points(self) -> None:
        reg = MetricsRegistry()
        reg.counter("a").increment()
        reg.gauge("b").set(Decimal("5"))
        points = reg.get_all_points()
        assert len(points) == 2
        names = {p.name for p in points}
        assert names == {"a", "b"}

    def test_names_lists(self) -> None:
        reg = MetricsRegistry()
        reg.counter("c1")
        reg.gauge("g1")
        reg.histogram("h1")
        assert "c1" in reg.counter_names
        assert "g1" in reg.gauge_names
        assert "h1" in reg.histogram_names
