from decimal import Decimal
from enum import StrEnum
from time import monotonic

from pydantic import BaseModel, Field

from utils.time_utils import utc_now_ms


class MetricType(StrEnum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class MetricPoint(BaseModel):
    name: str
    value: Decimal
    metric_type: MetricType
    timestamp: int = Field(default_factory=utc_now_ms)
    tags: dict[str, str] = Field(default_factory=dict)


class Counter:
    def __init__(self, name: str, tags: dict[str, str] | None = None) -> None:
        self._name = name
        self._value = Decimal("0")
        self._tags = tags or {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> Decimal:
        return self._value

    def increment(self, amount: Decimal = Decimal("1")) -> None:
        self._value += amount

    def reset(self) -> None:
        self._value = Decimal("0")

    def to_point(self) -> MetricPoint:
        return MetricPoint(
            name=self._name,
            value=self._value,
            metric_type=MetricType.COUNTER,
            tags=self._tags,
        )


class Gauge:
    def __init__(self, name: str, tags: dict[str, str] | None = None) -> None:
        self._name = name
        self._value = Decimal("0")
        self._tags = tags or {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> Decimal:
        return self._value

    def set(self, value: Decimal) -> None:
        self._value = value

    def to_point(self) -> MetricPoint:
        return MetricPoint(
            name=self._name,
            value=self._value,
            metric_type=MetricType.GAUGE,
            tags=self._tags,
        )


class Histogram:
    def __init__(self, name: str, tags: dict[str, str] | None = None) -> None:
        self._name = name
        self._values: list[Decimal] = []
        self._tags = tags or {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def count(self) -> int:
        return len(self._values)

    def observe(self, value: Decimal) -> None:
        self._values.append(value)

    @property
    def mean(self) -> Decimal:
        if not self._values:
            return Decimal("0")
        return sum(self._values) / Decimal(str(len(self._values)))

    @property
    def p50(self) -> Decimal:
        return self._percentile(50)

    @property
    def p95(self) -> Decimal:
        return self._percentile(95)

    @property
    def p99(self) -> Decimal:
        return self._percentile(99)

    def _percentile(self, pct: int) -> Decimal:
        if not self._values:
            return Decimal("0")
        sorted_vals = sorted(self._values)
        idx = max(0, int(len(sorted_vals) * pct / 100) - 1)
        return sorted_vals[idx]

    def reset(self) -> None:
        self._values.clear()


class LatencyTracker:
    def __init__(self, histogram: Histogram) -> None:
        self._histogram = histogram
        self._start: float | None = None

    def start(self) -> None:
        self._start = monotonic()

    def stop(self) -> None:
        if self._start is not None:
            elapsed_ms = Decimal(str(round((monotonic() - self._start) * 1000, 3)))
            self._histogram.observe(elapsed_ms)
            self._start = None

    @property
    def histogram(self) -> Histogram:
        return self._histogram


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str, tags: dict[str, str] | None = None) -> Counter:
        if name not in self._counters:
            self._counters[name] = Counter(name, tags)
        return self._counters[name]

    def gauge(self, name: str, tags: dict[str, str] | None = None) -> Gauge:
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, tags)
        return self._gauges[name]

    def histogram(self, name: str, tags: dict[str, str] | None = None) -> Histogram:
        if name not in self._histograms:
            self._histograms[name] = Histogram(name, tags)
        return self._histograms[name]

    def latency_tracker(self, name: str) -> LatencyTracker:
        return LatencyTracker(self.histogram(name))

    def get_all_points(self) -> list[MetricPoint]:
        points: list[MetricPoint] = []
        for c in self._counters.values():
            points.append(c.to_point())
        for g in self._gauges.values():
            points.append(g.to_point())
        return points

    @property
    def counter_names(self) -> list[str]:
        return list(self._counters.keys())

    @property
    def gauge_names(self) -> list[str]:
        return list(self._gauges.keys())

    @property
    def histogram_names(self) -> list[str]:
        return list(self._histograms.keys())
