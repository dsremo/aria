"""Tests for Alert Notification System."""

import tempfile
import time

import pytest

from aria.notifications.alerter import (
    Alert,
    AlertNotifier,
    CallbackChannel,
    ConsoleChannel,
    FileChannel,
)


class TestAlert:
    def test_create_alert(self) -> None:
        a = Alert(severity="CRITICAL", subsystem="power", message="Battery low")
        assert a.severity == "CRITICAL"
        assert a.is_critical

    def test_alert_timestamp(self) -> None:
        a = Alert(severity="WARNING", subsystem="thermal", message="Temp high")
        assert a.timestamp > 0

    def test_alert_to_dict(self) -> None:
        a = Alert(severity="EMERGENCY", subsystem="hull", message="Breach")
        d = a.to_dict()
        assert d["severity"] == "EMERGENCY"
        assert "timestamp" in d

    def test_alert_to_json(self) -> None:
        a = Alert(severity="WATCH", subsystem="nav", message="Drift")
        j = a.to_json()
        assert '"WATCH"' in j

    def test_is_critical(self) -> None:
        assert Alert(severity="CRITICAL", subsystem="x", message="y").is_critical
        assert Alert(severity="EMERGENCY", subsystem="x", message="y").is_critical
        assert not Alert(severity="WARNING", subsystem="x", message="y").is_critical


class TestConsoleChannel:
    def test_sends_warning(self, capsys) -> None:
        ch = ConsoleChannel(min_severity="WARNING")
        ch.send(Alert(severity="WARNING", subsystem="power", message="Low"))
        captured = capsys.readouterr()
        assert "power" in captured.out
        assert "Low" in captured.out

    def test_filters_below_min(self, capsys) -> None:
        ch = ConsoleChannel(min_severity="CRITICAL")
        ch.send(Alert(severity="WARNING", subsystem="x", message="y"))
        captured = capsys.readouterr()
        assert captured.out == ""


class TestFileChannel:
    def test_writes_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="r", suffix=".log", delete=False) as f:
            path = f.name
        ch = FileChannel(path)
        ch.send(Alert(severity="CRITICAL", subsystem="power", message="Battery"))
        with open(path) as f:
            content = f.read()
        assert "CRITICAL" in content
        assert "Battery" in content


class TestCallbackChannel:
    def test_callback_called(self) -> None:
        received = []
        ch = CallbackChannel(lambda a: received.append(a))
        ch.send(Alert(severity="WARNING", subsystem="x", message="test"))
        assert len(received) == 1
        assert received[0].message == "test"


class TestAlertNotifier:
    def test_notify_to_callback(self) -> None:
        received = []
        notifier = AlertNotifier()
        notifier.add_channel(CallbackChannel(lambda a: received.append(a)))
        count = notifier.notify(Alert(severity="CRITICAL", subsystem="hull", message="Breach"))
        assert count == 1
        assert len(received) == 1

    def test_multiple_channels(self) -> None:
        r1, r2 = [], []
        notifier = AlertNotifier()
        notifier.add_channel(CallbackChannel(lambda a: r1.append(a), name="ch1"))
        notifier.add_channel(CallbackChannel(lambda a: r2.append(a), name="ch2"))
        notifier.notify(Alert(severity="WARNING", subsystem="x", message="y"))
        assert len(r1) == 1
        assert len(r2) == 1

    def test_remove_channel(self) -> None:
        r1 = []
        notifier = AlertNotifier()
        notifier.add_channel(CallbackChannel(lambda a: r1.append(a), name="ch1"))
        notifier.remove_channel("ch1")
        notifier.notify(Alert(severity="WARNING", subsystem="x", message="y"))
        assert len(r1) == 0

    def test_rate_limiting(self) -> None:
        received = []
        notifier = AlertNotifier()
        notifier._rate_limit = 5
        notifier.add_channel(CallbackChannel(lambda a: received.append(a)))
        for i in range(20):
            notifier.notify(Alert(severity="WARNING", subsystem="power", message=f"Alert {i}"))
        assert len(received) == 5  # Rate limited

    def test_history(self) -> None:
        notifier = AlertNotifier()
        notifier.add_channel(CallbackChannel(lambda a: None))
        for i in range(10):
            notifier.notify(Alert(severity="WARNING", subsystem="x", message=f"msg {i}"))
        assert len(notifier.recent(5)) == 5

    def test_notify_from_event(self) -> None:
        received = []
        notifier = AlertNotifier()
        notifier.add_channel(CallbackChannel(lambda a: received.append(a)))
        notifier.notify_from_event({
            "severity": "CRITICAL",
            "subsystem": "propulsion",
            "message": "Fuel exhausted",
            "year": 500,
        })
        assert len(received) == 1
        assert received[0].subsystem == "propulsion"
        assert received[0].mission_year == 500

    def test_stats(self) -> None:
        notifier = AlertNotifier()
        notifier.add_channel(CallbackChannel(lambda a: None, name="test"))
        notifier.notify(Alert(severity="WARNING", subsystem="x", message="y"))
        stats = notifier.stats
        assert stats["channels"] == 1
        assert stats["total_sent"] == 1

    def test_recent_by_severity(self) -> None:
        notifier = AlertNotifier()
        notifier.add_channel(CallbackChannel(lambda a: None))
        notifier.notify(Alert(severity="WARNING", subsystem="x", message="w"))
        notifier.notify(Alert(severity="CRITICAL", subsystem="x", message="c"))
        notifier.notify(Alert(severity="WARNING", subsystem="x", message="w2"))
        criticals = notifier.recent_by_severity("CRITICAL")
        assert len(criticals) == 1
        assert criticals[0].message == "c"
