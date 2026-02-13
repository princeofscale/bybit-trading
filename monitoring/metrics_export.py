from monitoring.metrics import MetricsRegistry


def _sanitize_name(name: str) -> str:
    return name.replace(".", "_").replace("-", "_").replace(" ", "_")


def to_prometheus_text(registry: MetricsRegistry) -> str:
    lines: list[str] = []

    for name in registry.counter_names:
        counter = registry.counter(name)
        safe = _sanitize_name(name)
        lines.append(f"# TYPE {safe} counter")
        lines.append(f"{safe} {float(counter.value)}")

    for name in registry.gauge_names:
        gauge = registry.gauge(name)
        safe = _sanitize_name(name)
        lines.append(f"# TYPE {safe} gauge")
        lines.append(f"{safe} {float(gauge.value)}")

    for name in registry.histogram_names:
        hist = registry.histogram(name)
        safe = _sanitize_name(name)
        lines.append(f"# TYPE {safe} summary")
        lines.append(f"{safe}_count {hist.count}")
        lines.append(f"{safe}_mean {float(hist.mean)}")
        lines.append(f'{safe}{{quantile="0.5"}} {float(hist.p50)}')
        lines.append(f'{safe}{{quantile="0.95"}} {float(hist.p95)}')
        lines.append(f'{safe}{{quantile="0.99"}} {float(hist.p99)}')

    lines.append("")
    return "\n".join(lines)
