"""Tests for ARIA safety system — checkpoint, health, safe mode."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.safety.checkpoint import CheckpointManager
from aria.safety.health import HealthScorer, HealthReport
from aria.safety.safe_mode import SafeModeManager, SafeLevel


# --- Checkpoint Tests ---

class TestCheckpoint:
    def test_save_and_restore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(persist_dir=tmpdir, interval_s=9999)
            state = {"agents": {"telemetry": "READY"}, "battery_soc": 85}

            # Save
            loop = asyncio.new_event_loop()
            mgr._state_provider = lambda: state
            cp = loop.run_until_complete(mgr.save_now())
            assert cp.checkpoint_id == 1
            assert cp.checksum

            # Restore
            restored = mgr.restore_latest()
            assert restored is not None
            assert restored["battery_soc"] == 85
            assert restored["agents"]["telemetry"] == "READY"
            loop.close()

    def test_checksum_detects_corruption(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(persist_dir=tmpdir)
            mgr._state_provider = lambda: {"key": "value"}

            loop = asyncio.new_event_loop()
            loop.run_until_complete(mgr.save_now())

            # Corrupt the checkpoint
            files = list(Path(tmpdir).glob("checkpoint_*.json"))
            for f in files:
                if not f.name.endswith(".bak"):
                    data = json.loads(f.read_text())
                    data["checksum"] = "corrupted"
                    f.write_text(json.dumps(data))

            # Restore should fall back to backup
            restored = mgr.restore_latest()
            assert restored is not None  # Backup should work
            loop.close()

    def test_cleanup_old_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(persist_dir=tmpdir, max_checkpoints=3)
            mgr._state_provider = lambda: {"i": 0}

            loop = asyncio.new_event_loop()
            for i in range(5):
                mgr._state_provider = lambda i=i: {"i": i}
                loop.run_until_complete(mgr.save_now())

            files = list(Path(tmpdir).glob("checkpoint_*.json"))
            files = [f for f in files if not f.name.endswith(".bak")]
            assert len(files) <= 3
            loop.close()


# --- Health Scorer Tests ---

class TestHealthScorer:
    def _all_ready(self) -> dict[str, str]:
        return {s: "READY" for s in ["eclss", "power", "navigation", "thermal",
                                      "telemetry", "comms", "propulsion", "science"]}

    def test_all_nominal(self):
        scorer = HealthScorer()
        report = scorer.compute(agent_statuses=self._all_ready())
        assert report.overall_score >= 90
        assert report.recommendation == "All systems nominal. No action required."

    def test_degraded_agent(self):
        scorer = HealthScorer()
        statuses = self._all_ready()
        statuses["power"] = "DEGRADED"
        report = scorer.compute(agent_statuses=statuses)
        assert report.overall_score < 100
        assert "power" in report.degraded_subsystems

    def test_critical_agent(self):
        scorer = HealthScorer()
        statuses = self._all_ready()
        statuses["eclss"] = "ERROR"
        statuses["power"] = "ERROR"
        report = scorer.compute(agent_statuses=statuses)
        assert report.overall_score < 70
        assert len(report.critical_subsystems) >= 2

    def test_stopped_agent_scores_zero(self):
        scorer = HealthScorer()
        statuses = self._all_ready()
        statuses["eclss"] = "STOPPED"
        report = scorer.compute(agent_statuses=statuses)
        assert report.subsystem_scores["eclss"] == 0.0
        assert "eclss" in report.critical_subsystems


# --- Safe Mode Tests ---

class TestSafeMode:
    @pytest.fixture
    def bus_and_manager(self):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        loop.run_until_complete(bus.start())
        mgr = SafeModeManager(bus)
        yield bus, mgr
        loop.run_until_complete(bus.stop())
        loop.close()

    def test_initial_level_is_nominal(self, bus_and_manager):
        _, mgr = bus_and_manager
        assert mgr.current_level == SafeLevel.NOMINAL

    def test_evaluate_escalation_on_low_health(self, bus_and_manager):
        _, mgr = bus_and_manager
        new_level = mgr.evaluate(health_score=35)
        assert new_level is not None
        assert new_level > SafeLevel.NOMINAL

    def test_evaluate_no_change_when_healthy(self, bus_and_manager):
        _, mgr = bus_and_manager
        new_level = mgr.evaluate(health_score=95)
        assert new_level is None

    def test_evaluate_survival_on_critical_battery(self, bus_and_manager):
        _, mgr = bus_and_manager
        new_level = mgr.evaluate(health_score=15, battery_soc=5)
        assert new_level == SafeLevel.SURVIVAL

    def test_config_for_level(self, bus_and_manager):
        _, mgr = bus_and_manager
        config = mgr.config
        assert "telemetry" in config.active_agents
        assert config.description  # Non-empty


# ---------------------------------------------------------------------------
# Detailed HealthScorer Tests
# ---------------------------------------------------------------------------

class TestHealthScorerDetailed:
    """Comprehensive tests covering weight semantics, edge cases, and reports."""

    def _all_ready(self) -> dict[str, str]:
        return {s: "READY" for s in [
            "eclss", "power", "navigation", "thermal",
            "telemetry", "comms", "propulsion", "science",
        ]}

    # 1
    def test_single_critical_subsystem_dominates_score(self):
        """If ECLSS (weight 25%) is ERROR, overall score drops below 80
        even when every other subsystem is READY."""
        scorer = HealthScorer()
        statuses = self._all_ready()
        statuses["eclss"] = "ERROR"  # ERROR → 0.1 * 100 = 10

        report = scorer.compute(agent_statuses=statuses)

        # Weighted contribution: eclss gives 10 * 0.25 = 2.5 instead of 25
        # Other 75% of weight is at 100 → 75.  Total ≈ 77.5
        assert report.overall_score < 80, (
            f"ECLSS ERROR should drag score below 80, got {report.overall_score}"
        )
        assert "eclss" in report.critical_subsystems, (
            "ECLSS at ERROR should appear in critical_subsystems"
        )
        # Verify the exact subsystem score for eclss
        assert report.subsystem_scores["eclss"] == 10.0, (
            f"ERROR status should map to score 10.0, got {report.subsystem_scores['eclss']}"
        )

    # 2
    def test_degraded_subsystem_partial_weight(self):
        """DEGRADED agents receive partial credit (0.6 * 100 = 60)."""
        scorer = HealthScorer()
        statuses = self._all_ready()
        statuses["power"] = "DEGRADED"

        report = scorer.compute(agent_statuses=statuses)

        assert report.subsystem_scores["power"] == 60.0, (
            f"DEGRADED should yield 60.0, got {report.subsystem_scores['power']}"
        )
        # power at 60 is in degraded band (50 <= score < 80)
        assert "power" in report.degraded_subsystems
        assert "power" not in report.critical_subsystems

        # Overall: power contributes 60 * 0.20 = 12 instead of 20
        # Other 80% of weight at 100 → 80.  Total ≈ 92 → still above 90
        # (but strictly less than 100)
        assert report.overall_score < 100
        assert report.overall_score > 80

    # 3
    def test_all_agents_error_near_zero(self):
        """All subsystems in ERROR → overall score near 0 (specifically 10,
        since ERROR maps to 0.1)."""
        scorer = HealthScorer()
        statuses = {s: "ERROR" for s in self._all_ready()}

        report = scorer.compute(agent_statuses=statuses)

        # Every subsystem scores 10.0, weighted average = 10.0
        assert report.overall_score == 10.0, (
            f"All ERROR should yield 10.0, got {report.overall_score}"
        )
        # Every subsystem should be critical (score < 50)
        assert len(report.critical_subsystems) == len(statuses), (
            "All subsystems should be in critical_subsystems"
        )
        assert "RECOMMEND SAFE MODE" in report.recommendation

    # 4
    def test_missing_subsystem_defaults_to_ready(self):
        """Subsystems not present in agent_statuses default to STOPPED (score 0).
        An agent name not matching any SUBSYSTEM_WEIGHTS key doesn't crash."""
        scorer = HealthScorer()

        # Only provide a couple of agents; others fall back to STOPPED
        statuses = {"eclss": "READY", "power": "READY"}
        report = scorer.compute(agent_statuses=statuses)

        # navigation, thermal, telemetry, comms, propulsion, science → STOPPED → 0
        for sub in ["navigation", "thermal", "telemetry", "comms", "propulsion", "science"]:
            assert report.subsystem_scores[sub] == 0.0, (
                f"Missing subsystem '{sub}' should default to 0.0"
            )
            assert sub in report.critical_subsystems

        # Unknown agent names (not in SUBSYSTEM_WEIGHTS) are simply ignored — no crash
        statuses_with_unknown = {**self._all_ready(), "mystery_agent": "READY"}
        report2 = scorer.compute(agent_statuses=statuses_with_unknown)
        assert report2.overall_score >= 90  # unknown key doesn't affect score

    # 5
    def test_health_report_lists_critical_and_degraded(self):
        """Verify the report correctly separates critical (< 50) and
        degraded (50-79) subsystems with multiple affected systems."""
        scorer = HealthScorer()
        statuses = self._all_ready()
        statuses["eclss"] = "ERROR"       # score 10 → critical
        statuses["power"] = "STOPPED"      # score 0  → critical
        statuses["navigation"] = "DEGRADED"  # score 60 → degraded
        statuses["comms"] = "DEGRADED"     # score 60 → degraded

        report = scorer.compute(agent_statuses=statuses)

        assert "eclss" in report.critical_subsystems
        assert "power" in report.critical_subsystems
        assert "navigation" in report.degraded_subsystems
        assert "comms" in report.degraded_subsystems

        # Critical subsystems should NOT also be in degraded list
        for sub in report.critical_subsystems:
            assert sub not in report.degraded_subsystems, (
                f"{sub} should not appear in both critical and degraded lists"
            )

        # Overall score check: significant degradation
        assert report.overall_score < 70, (
            f"Multiple critical+degraded should drop score below 70, got {report.overall_score}"
        )
        # Recommendation should reference critical subsystems
        assert "Critical" in report.recommendation or "critical" in report.recommendation.lower()


# ---------------------------------------------------------------------------
# Detailed SafeModeManager Tests
# ---------------------------------------------------------------------------

class TestSafeModeDetailed:
    """Comprehensive tests for evaluate(), transition(), and per-level configs."""

    @pytest.fixture
    def bus_and_manager(self):
        loop = asyncio.new_event_loop()
        bus = MessageBus()
        loop.run_until_complete(bus.start())
        mgr = SafeModeManager(bus)
        yield loop, bus, mgr
        loop.run_until_complete(bus.stop())
        loop.close()

    # 6
    def test_evaluate_nominal_to_reduced(self, bus_and_manager):
        """Health score of 55 (below 60 threshold for REDUCED_AUTONOMY and
        below 80 for REDUCED_SCIENCE) triggers at least REDUCED_SCIENCE."""
        _, _, mgr = bus_and_manager
        assert mgr.current_level == SafeLevel.NOMINAL

        new_level = mgr.evaluate(health_score=55)
        assert new_level is not None
        assert new_level >= SafeLevel.REDUCED_SCIENCE, (
            f"Health 55 should trigger at least REDUCED_SCIENCE, got {new_level}"
        )

    # 7
    def test_evaluate_below_30_triggers_monitoring_only(self, bus_and_manager):
        """Very low health (< 40) triggers MONITORING_ONLY or higher."""
        _, _, mgr = bus_and_manager

        new_level = mgr.evaluate(health_score=25)
        assert new_level is not None
        assert new_level >= SafeLevel.MONITORING_ONLY, (
            f"Health 25 should trigger at least MONITORING_ONLY, got {new_level}"
        )

    # 8
    def test_evaluate_battery_critical(self, bus_and_manager):
        """battery_soc=5 triggers SURVIVAL regardless of health score."""
        _, _, mgr = bus_and_manager

        # Even with a decent health score, critical battery forces SURVIVAL
        new_level = mgr.evaluate(health_score=90, battery_soc=5)
        assert new_level == SafeLevel.SURVIVAL, (
            f"battery_soc=5 should trigger SURVIVAL, got {new_level}"
        )

    # 9
    def test_transition_publishes_event(self, bus_and_manager):
        """transition() publishes an aria.safety.mode_change message on the bus."""
        loop, bus, mgr = bus_and_manager

        captured_messages: list[Message] = []

        async def capture(msg: Message) -> None:
            captured_messages.append(msg)

        bus.subscribe("aria.safety.mode_change", capture)

        # Execute the transition
        loop.run_until_complete(
            mgr.transition(SafeLevel.REDUCED_SCIENCE, reason="health degraded")
        )

        # Give the dispatch loop a moment to deliver the message
        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(captured_messages) >= 1, (
            "transition() should publish at least one aria.safety.mode_change message"
        )
        msg = captured_messages[0]
        assert msg.topic == "aria.safety.mode_change"
        assert msg.payload["direction"] == "ESCALATED"
        assert msg.payload["from_level"] == "NOMINAL"
        assert msg.payload["to_level"] == "REDUCED_SCIENCE"
        assert msg.payload["reason"] == "health degraded"
        assert "active_agents" in msg.payload["config"]
        assert msg.source_agent == "safe_mode_manager"

        # Verify the manager state updated
        assert mgr.current_level == SafeLevel.REDUCED_SCIENCE
        history = mgr.get_history()
        assert len(history) == 1
        assert history[0]["from"] == "NOMINAL"
        assert history[0]["to"] == "REDUCED_SCIENCE"

    # 10
    def test_config_for_each_level(self, bus_and_manager):
        """Every SafeLevel has a valid SafeLevelConfig with required fields."""
        from aria.safety.safe_mode import LEVEL_CONFIGS, SafeLevelConfig

        for level in SafeLevel:
            assert level in LEVEL_CONFIGS, f"Missing config for {level.name}"
            cfg = LEVEL_CONFIGS[level]
            assert isinstance(cfg, SafeLevelConfig)
            assert cfg.level == level
            assert isinstance(cfg.active_agents, list)
            assert len(cfg.active_agents) > 0, (
                f"{level.name} must have at least one active agent"
            )
            assert cfg.description, f"{level.name} must have a description"
            assert cfg.max_authority is not None

        # SURVIVAL should have the fewest active agents
        survival_agents = len(LEVEL_CONFIGS[SafeLevel.SURVIVAL].active_agents)
        nominal_agents = len(LEVEL_CONFIGS[SafeLevel.NOMINAL].active_agents)
        assert survival_agents < nominal_agents, (
            "SURVIVAL should have fewer active agents than NOMINAL"
        )


# ---------------------------------------------------------------------------
# Detailed CheckpointManager Tests
# ---------------------------------------------------------------------------

class TestCheckpointDetailed:
    """Comprehensive tests for multi-checkpoint saves, restore ordering, and integrity."""

    # 11
    def test_multiple_checkpoints_saved(self):
        """Save 3 checkpoints, verify all exist on disk with correct IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(persist_dir=tmpdir, interval_s=9999, max_checkpoints=10)

            states = [
                {"mission_phase": "LEO", "tick": 1},
                {"mission_phase": "LEO", "tick": 2},
                {"mission_phase": "TRANSFER", "tick": 3},
            ]

            loop = asyncio.new_event_loop()
            checkpoints = []
            for state in states:
                mgr._state_provider = lambda s=state: s
                cp = loop.run_until_complete(mgr.save_now())
                checkpoints.append(cp)

            # Verify checkpoint IDs are sequential
            assert [cp.checkpoint_id for cp in checkpoints] == [1, 2, 3]

            # Verify files exist on disk (primary + backup for each)
            primary_files = sorted(
                f for f in Path(tmpdir).glob("checkpoint_*.json")
                if not f.name.endswith(".bak")
            )
            backup_files = sorted(Path(tmpdir).glob("checkpoint_*.json.bak"))
            assert len(primary_files) == 3, (
                f"Expected 3 primary checkpoint files, found {len(primary_files)}"
            )
            assert len(backup_files) == 3, (
                f"Expected 3 backup files, found {len(backup_files)}"
            )

            # Verify each checkpoint has a non-empty checksum
            for cp in checkpoints:
                assert cp.checksum, f"Checkpoint {cp.checkpoint_id} has empty checksum"
                assert cp.size_bytes > 0

            loop.close()

    # 12
    def test_restore_returns_latest(self):
        """restore_latest() returns the most recent checkpoint's state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(persist_dir=tmpdir, interval_s=9999, max_checkpoints=10)

            loop = asyncio.new_event_loop()
            for i in range(1, 4):
                mgr._state_provider = lambda i=i: {"version": i, "data": f"state_{i}"}
                loop.run_until_complete(mgr.save_now())

            restored = mgr.restore_latest()
            assert restored is not None
            assert restored["version"] == 3, (
                f"Expected latest version 3, got {restored['version']}"
            )
            assert restored["data"] == "state_3"

            # Also verify last_checkpoint property tracks the most recent
            assert mgr.last_checkpoint is not None
            assert mgr.last_checkpoint.checkpoint_id == 3

            loop.close()

    # 13
    def test_checkpoint_integrity(self):
        """Saved checkpoint checksum matches recomputed checksum from the stored data,
        proving state_data was not corrupted during serialization."""
        import hashlib as _hashlib

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(persist_dir=tmpdir, interval_s=9999)
            test_state = {
                "agents": {"eclss": "READY", "power": "DEGRADED"},
                "battery_soc": 42.7,
                "mission_time_s": 86400,
                "nested": {"list": [1, 2, 3], "flag": True},
            }
            mgr._state_provider = lambda: test_state

            loop = asyncio.new_event_loop()
            cp = loop.run_until_complete(mgr.save_now())

            # Recompute checksum from state_data the same way Checkpoint does
            raw = json.dumps(cp.state_data, sort_keys=True, default=str).encode()
            expected_checksum = _hashlib.sha256(raw).hexdigest()[:16]
            assert cp.checksum == expected_checksum, (
                f"Checksum mismatch: stored={cp.checksum}, computed={expected_checksum}"
            )

            # Also verify the on-disk file has the same checksum
            primary_files = [
                f for f in Path(tmpdir).glob("checkpoint_*.json")
                if not f.name.endswith(".bak")
            ]
            assert len(primary_files) == 1
            disk_data = json.loads(primary_files[0].read_text())
            assert disk_data["checksum"] == expected_checksum, (
                "On-disk checksum should match computed checksum"
            )

            # Verify restore_latest also yields the same state
            restored = mgr.restore_latest()
            assert restored == test_state, (
                "Restored state should exactly match original test_state"
            )

            loop.close()
