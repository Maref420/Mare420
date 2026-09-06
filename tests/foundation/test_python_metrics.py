"""Tests for foundation/metrics/python_metrics.py — stdlib metrics collector.

Governance: Verifies thread-safety, Prometheus export format, and contract compliance.
"""
from __future__ import annotations

import threading

from foundation.metrics.python_metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
)


class TestCounter:
    def test_increment_default(self) -> None:
        c = Counter("test_counter_total", "A test counter")
        c.increment()
        assert c.value == 1.0

    def test_increment_custom(self) -> None:
        c = Counter("test_counter_total", "A test counter")
        c.increment(5.0)
        assert c.value == 5.0

    def test_thread_safety(self) -> None:
        c = Counter("test_counter_total", "A test counter")
        threads = [threading.Thread(target=lambda: [c.increment() for _ in range(100)]) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c.value == 1000.0


class TestGauge:
    def test_set_and_read(self) -> None:
        g = Gauge("test_gauge", "A test gauge")
        g.set(42.0)
        assert g.value == 42.0

    def test_inc_dec(self) -> None:
        g = Gauge("test_gauge", "A test gauge")
        g.inc(10.0)
        g.dec(3.0)
        assert g.value == 7.0


class TestHistogram:
    def test_observe(self) -> None:
        h = Histogram("test_histogram", "A test histogram")
        h.observe(0.5)
        h.observe(1.5)
        assert h.count == 2
        assert h.sum == 2.0

    def test_buckets(self) -> None:
        h = Histogram("test_histogram", "A test histogram")
        h.observe(0.003)
        buckets = h.buckets
        assert buckets[0.005] == 1
        assert buckets[0.01] == 1

    def test_custom_buckets(self) -> None:
        h = Histogram("test_histogram", "A test histogram", buckets=(1.0, 5.0, 10.0))
        h.observe(3.0)
        assert h.buckets[1.0] == 0
        assert h.buckets[5.0] == 1


class TestMetricsRegistry:
    def test_register_and_get(self) -> None:
        reg = MetricsRegistry()
        c = Counter("reg_counter_total", "Registered counter")
        reg.register(c)
        assert reg.get("reg_counter_total") is c

    def test_get_missing_returns_none(self) -> None:
        reg = MetricsRegistry()
        assert reg.get("nonexistent") is None

    def test_export_prometheus_format(self) -> None:
        reg = MetricsRegistry()
        c = Counter("export_counter_total", "Export test counter")
        c.increment(42.0)
        g = Gauge("export_gauge", "Export test gauge")
        g.set(3.14)
        reg.register(c)
        reg.register(g)
        output = reg.export_prometheus()
        assert "# HELP export_counter_total Export test counter" in output
        assert "# TYPE export_counter_total counter" in output
        assert "export_counter_total 42.000000" in output
        assert "# HELP export_gauge Export test gauge" in output
        assert "export_gauge 3.140000" in output

    def test_export_histogram(self) -> None:
        reg = MetricsRegistry()
        h = Histogram("export_hist", "Export test histogram")
        h.observe(0.5)
        reg.register(h)
        output = reg.export_prometheus()
        assert "export_hist_count 1" in output
        assert "export_hist_sum 0.500000" in output
        assert 'export_hist_bucket{le="+Inf"} 1' in output
