"""Tests for ARIA metrics collector."""

from aria.metrics.collector import MetricsCollector


def test_counter():
    mc = MetricsCollector()
    mc.increment("tool.calls")
    mc.increment("tool.calls")
    mc.increment("tool.calls", 3)
    assert mc.get_counter("tool.calls") == 5


def test_gauge():
    mc = MetricsCollector()
    mc.gauge("cpu.percent", 45.2)
    assert mc.get_gauge("cpu.percent") == 45.2
    mc.gauge("cpu.percent", 52.0)
    assert mc.get_gauge("cpu.percent") == 52.0


def test_latency_histogram():
    mc = MetricsCollector()
    for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        mc.record_latency("tool.dsremo", float(v))

    hist = mc.get_histogram("tool.dsremo")
    assert hist is not None
    assert hist.count == 10
    assert hist.p50 == 60  # Median of 10-100
    assert hist.p95 >= 90
    assert hist.p99 >= 90


def test_snapshot():
    mc = MetricsCollector()
    mc.increment("requests")
    mc.gauge("memory_mb", 512)
    mc.record_latency("response", 25.0)

    snap = mc.snapshot()
    assert snap["counters"]["requests"] == 1
    assert snap["gauges"]["memory_mb"] == 512
    assert "response" in snap["histograms"]
    assert snap["uptime_s"] >= 0


def test_reset():
    mc = MetricsCollector()
    mc.increment("x")
    mc.gauge("y", 1.0)
    mc.record_latency("z", 5.0)
    mc.reset()
    assert mc.get_counter("x") == 0
    assert mc.get_gauge("y") == 0.0
    assert mc.get_histogram("z") is None


def test_gauge_overwrites():
    mc = MetricsCollector()
    mc.gauge("temp", 100.0)
    mc.gauge("temp", 200.0)
    mc.gauge("temp", 300.0)
    assert mc.get_gauge("temp") == 300.0


def test_histogram_empty():
    mc = MetricsCollector()
    assert mc.get_histogram("nonexistent") is None


def test_snapshot_structure():
    mc = MetricsCollector()
    snap = mc.snapshot()
    assert "counters" in snap
    assert "gauges" in snap
    assert "histograms" in snap


def test_reset_clears_all():
    mc = MetricsCollector()
    mc.increment("a", 10)
    mc.increment("b", 20)
    mc.gauge("g1", 1.0)
    mc.gauge("g2", 2.0)
    mc.record_latency("h", 5.0)
    mc.reset()
    assert mc.get_counter("a") == 0
    assert mc.get_counter("b") == 0
    assert mc.get_gauge("g1") == 0.0
    assert mc.get_gauge("g2") == 0.0
    assert mc.get_histogram("h") is None
    snap = mc.snapshot()
    assert snap["counters"] == {}
    assert snap["gauges"] == {}
    assert snap["histograms"] == {}


def test_multiple_histograms():
    mc = MetricsCollector()
    mc.record_latency("api.latency", 10.0)
    mc.record_latency("api.latency", 20.0)
    mc.record_latency("db.latency", 100.0)
    mc.record_latency("db.latency", 200.0)

    api_hist = mc.get_histogram("api.latency")
    db_hist = mc.get_histogram("db.latency")

    assert api_hist is not None
    assert db_hist is not None
    assert api_hist.count == 2
    assert db_hist.count == 2
    assert api_hist.mean != db_hist.mean
