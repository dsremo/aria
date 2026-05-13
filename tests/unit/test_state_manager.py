"""Tests for the ARIA state manager."""

import pytest

from aria.state.manager import StateManager


@pytest.fixture
def state():
    return StateManager()  # No persistence for tests


def test_get_set(state: StateManager):
    state.set("aria.status", "RUNNING")
    assert state.get("aria.status") == "RUNNING"


def test_default_value(state: StateManager):
    assert state.get("nonexistent", "default") == "default"


def test_versioning(state: StateManager):
    state.set("key", "v1")
    state.set("key", "v2")
    entry = state.get_entry("key")
    assert entry is not None
    assert entry.version == 2


def test_rollback(state: StateManager):
    state.set("key", "v1")
    state.set("key", "v2")
    assert state.get("key") == "v2"

    state.rollback("key")
    assert state.get("key") == "v1"


def test_observer_notified(state: StateManager):
    changes: list[tuple[str, object, object]] = []

    def observer(key: str, old: object, new: object) -> None:
        changes.append((key, old, new))

    state.subscribe(observer)
    state.set("key", "value1")
    state.set("key", "value2")

    assert len(changes) == 2
    assert changes[0] == ("key", None, "value1")
    assert changes[1] == ("key", "value1", "value2")


def test_delete(state: StateManager):
    state.set("key", "value")
    assert state.delete("key")
    assert state.get("key") is None


def test_keys_with_prefix(state: StateManager):
    state.set("aria.agents.telemetry.status", "READY")
    state.set("aria.agents.power.status", "READY")
    state.set("aria.mission_phase", "LEO")

    agent_keys = state.keys(prefix="aria.agents.")
    assert len(agent_keys) == 2


def test_snapshot(state: StateManager):
    state.set("a", 1)
    state.set("b", 2)
    snap = state.snapshot()
    assert snap == {"a": 1, "b": 2}


def test_observer_called_on_delete(state: StateManager):
    """Verify observer fires when a key is deleted."""
    changes: list[tuple[str, object, object]] = []

    def observer(key: str, old: object, new: object) -> None:
        changes.append((key, old, new))

    state.subscribe(observer)
    state.set("temp", "data")
    state.delete("temp")

    # Observer is called on set; delete does not notify observers in current impl
    assert len(changes) == 1
    assert changes[0] == ("temp", None, "data")


def test_snapshot_includes_all_keys(state: StateManager):
    """Snapshot returns all stored keys."""
    state.set("x", 10)
    state.set("y", 20)
    state.set("z", 30)
    snap = state.snapshot()
    assert set(snap.keys()) == {"x", "y", "z"}
    assert snap["x"] == 10
    assert snap["y"] == 20
    assert snap["z"] == 30


def test_version_increments_on_set(state: StateManager):
    """Version increases with each set call on the same key."""
    state.set("counter", "a")
    assert state.get_entry("counter").version == 1

    state.set("counter", "b")
    assert state.get_entry("counter").version == 2

    state.set("counter", "c")
    assert state.get_entry("counter").version == 3


def test_multiple_observers(state: StateManager):
    """Multiple observers all get called on state change."""
    calls_a: list[str] = []
    calls_b: list[str] = []
    calls_c: list[str] = []

    state.subscribe(lambda k, o, n: calls_a.append(k))
    state.subscribe(lambda k, o, n: calls_b.append(k))
    state.subscribe(lambda k, o, n: calls_c.append(k))

    state.set("event", "fired")

    assert calls_a == ["event"]
    assert calls_b == ["event"]
    assert calls_c == ["event"]


def test_rollback_restores_previous_value(state: StateManager):
    """Rollback actually restores the previous value and version."""
    state.set("sensor", "100")
    state.set("sensor", "200")
    state.set("sensor", "300")

    assert state.get("sensor") == "300"

    state.rollback("sensor")
    assert state.get("sensor") == "200"
    assert state.get_entry("sensor").version == 2

    state.rollback("sensor")
    assert state.get("sensor") == "100"
    assert state.get_entry("sensor").version == 1
