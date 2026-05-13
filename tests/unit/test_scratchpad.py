"""Tests for SharedScratchpad inter-agent state sharing."""

from __future__ import annotations

import time

from aria.state.scratchpad import SharedScratchpad


class TestSharedScratchpad:
    def setup_method(self):
        self.sp = SharedScratchpad()

    def test_write_and_read(self):
        self.sp.write("power.eclipse_state", {"in_eclipse": True}, "power")
        result = self.sp.read("power.eclipse_state")
        assert result == {"in_eclipse": True}

    def test_read_missing_key(self):
        assert self.sp.read("nonexistent") is None

    def test_overwrite(self):
        self.sp.write("power.soc", {"percent": 80}, "power")
        self.sp.write("power.soc", {"percent": 75}, "power")
        assert self.sp.read("power.soc") == {"percent": 75}

    def test_delete(self):
        self.sp.write("test.key", {"a": 1}, "test")
        assert self.sp.delete("test.key")
        assert self.sp.read("test.key") is None
        assert not self.sp.delete("test.key")  # Already deleted

    def test_ttl_expiry(self):
        self.sp.write("temp.data", {"x": 1}, "test", ttl_s=0.01)
        assert self.sp.read("temp.data") == {"x": 1}
        time.sleep(0.02)
        assert self.sp.read("temp.data") is None  # Expired

    def test_no_ttl_persists(self):
        self.sp.write("persistent", {"y": 2}, "test", ttl_s=0)
        time.sleep(0.01)
        assert self.sp.read("persistent") == {"y": 2}

    def test_keys_by_prefix(self):
        self.sp.write("power.soc", {"v": 1}, "power")
        self.sp.write("power.solar", {"v": 2}, "power")
        self.sp.write("nav.gps", {"v": 3}, "nav")
        keys = self.sp.keys_by_prefix("power.")
        assert set(keys) == {"power.soc", "power.solar"}

    def test_keys_by_agent(self):
        self.sp.write("power.soc", {"v": 1}, "power")
        self.sp.write("nav.gps", {"v": 2}, "navigation")
        self.sp.write("power.bus", {"v": 3}, "power")
        keys = self.sp.keys_by_agent("power")
        assert set(keys) == {"power.soc", "power.bus"}

    def test_all_entries(self):
        self.sp.write("a", {"v": 1}, "x")
        self.sp.write("b", {"v": 2}, "y")
        entries = self.sp.all_entries()
        assert len(entries) == 2
        assert entries["a"] == {"v": 1}

    def test_read_entry_metadata(self):
        self.sp.write("test", {"data": True}, "agent_x")
        entry = self.sp.read_entry("test")
        assert entry is not None
        assert entry.posted_by == "agent_x"
        assert entry.key == "test"

    def test_size(self):
        assert self.sp.size == 0
        self.sp.write("a", {}, "x")
        self.sp.write("b", {}, "y")
        assert self.sp.size == 2

    def test_size_after_expiry(self):
        """Size reflects expired entries being pruned."""
        self.sp.write("temp", {"x": 1}, "t", ttl_s=0.01)
        assert self.sp.size == 1
        time.sleep(0.02)
        assert self.sp.size == 0

    def test_cross_agent_sharing(self):
        """Simulate PowerAgent posting, ThermalAgent reading."""
        # PowerAgent posts eclipse state
        self.sp.write("power.eclipse_state", {
            "in_eclipse": True,
            "expected_duration_min": 35,
            "battery_soc_at_entry": 82.0,
        }, "power")

        # ThermalAgent reads it
        eclipse = self.sp.read("power.eclipse_state")
        assert eclipse["in_eclipse"] is True
        assert eclipse["expected_duration_min"] == 35

        # NavigationAgent posts conjunction data
        self.sp.write("nav.next_conjunction", {
            "object": "DEBRIS-2024-001",
            "pc": 1.2e-4,
            "tca_hours": 8.5,
        }, "navigation")

        # PropulsionAgent reads it
        conj = self.sp.read("nav.next_conjunction")
        assert conj["pc"] == 1.2e-4


class TestScratchpadAdvanced:
    def test_multiple_agents_write_same_key(self):
        """Later write overwrites earlier one for same key."""
        sp = SharedScratchpad()
        sp.write("test.key", {"v": 1}, "agent_a")
        sp.write("test.key", {"v": 2}, "agent_b")
        entry = sp.read_entry("test.key")
        assert entry.value == {"v": 2}
        assert entry.posted_by == "agent_b"

    def test_many_entries_performance(self):
        """Scratchpad handles 1000 entries without issue."""
        sp = SharedScratchpad()
        for i in range(1000):
            sp.write(f"perf.key.{i}", {"index": i}, f"agent_{i % 10}")
        assert sp.size == 1000
        assert sp.read("perf.key.500") == {"index": 500}

    def test_keys_by_prefix_after_expiry(self):
        """Expired entries don't appear in prefix search."""
        sp = SharedScratchpad()
        sp.write("test.a", {"v": 1}, "x", ttl_s=0.01)
        sp.write("test.b", {"v": 2}, "x", ttl_s=0)  # No expiry
        import time
        time.sleep(0.02)
        keys = sp.keys_by_prefix("test.")
        assert "test.a" not in keys
        assert "test.b" in keys


class TestScratchpadEdgeCases:
    def test_empty_value_ok(self):
        sp = SharedScratchpad()
        sp.write("empty", {}, "agent")
        assert sp.read("empty") == {}

    def test_nested_value(self):
        sp = SharedScratchpad()
        sp.write("nested", {"a": {"b": {"c": 1}}}, "agent")
        assert sp.read("nested")["a"]["b"]["c"] == 1

    def test_large_value(self):
        sp = SharedScratchpad()
        big = {f"key_{i}": i for i in range(1000)}
        sp.write("big", big, "agent")
        assert sp.read("big")["key_500"] == 500

    def test_special_characters_in_key(self):
        sp = SharedScratchpad()
        sp.write("power.eclipse_state.v2", {"ok": True}, "power")
        assert sp.read("power.eclipse_state.v2")["ok"] is True

    def test_overwrite_preserves_ttl(self):
        import time
        sp = SharedScratchpad()
        sp.write("key", {"v": 1}, "a", ttl_s=0.01)
        sp.write("key", {"v": 2}, "a", ttl_s=100)  # New TTL
        time.sleep(0.02)
        # Should still be readable (new TTL is 100s)
        assert sp.read("key") == {"v": 2}

    def test_read_entry_returns_none_for_missing(self):
        sp = SharedScratchpad()
        assert sp.read_entry("nonexistent") is None
