"""Tests for ARIA memory system."""

import pytest

from aria.memory.store import MemoryStore


@pytest.fixture
def memory():
    return MemoryStore()


def test_working_memory_push_and_get(memory: MemoryStore):
    memory.push_working({"event": "test", "value": 42})
    recent = memory.get_working(minutes_back=1.0)
    assert len(recent) == 1
    assert recent[0]["event"] == "test"


def test_working_memory_ring_buffer(memory: MemoryStore):
    memory._working_max = 5
    for i in range(10):
        memory.push_working({"i": i})
    assert len(memory._working) == 5
    assert memory._working[0]["i"] == 5


async def test_episodic_store_and_recall(memory: MemoryStore):
    await memory.store_episode(
        event_type="anomaly",
        summary="Battery SoC dropped to 15%",
        severity="WARNING",
        tags=["battery", "power"],
    )
    await memory.store_episode(
        event_type="maneuver",
        summary="Conjunction avoidance burn executed",
        tags=["maneuver", "conjunction"],
    )

    # Recall by query
    results = memory.recall_episodes(query="battery")
    assert len(results) >= 1
    assert "battery" in results[0].summary.lower()

    # Recall by event type
    results = memory.recall_episodes(event_type="maneuver")
    assert len(results) == 1


async def test_episodic_recall_empty(memory: MemoryStore):
    results = memory.recall_episodes(query="nonexistent")
    assert results == []


def test_procedure_add_and_search(memory: MemoryStore):
    memory.add_procedure(
        title="Fire Response Procedure",
        content="1. Sound alarm. 2. Deploy suppression.",
        category="emergency",
        subsystem="eclss",
        tags=["fire"],
    )
    memory.add_procedure(
        title="Eclipse Preparation",
        content="1. Check battery. 2. Pre-heat zones.",
        category="operations",
        subsystem="power",
        tags=["eclipse"],
    )

    results = memory.search_procedures("fire")
    assert len(results) >= 1
    assert "Fire" in results[0].title

    results = memory.search_procedures("eclipse")
    assert len(results) >= 1


def test_procedure_by_subsystem(memory: MemoryStore):
    memory.add_procedure(title="P1", content="...", subsystem="eclss")
    memory.add_procedure(title="P2", content="...", subsystem="power")
    memory.add_procedure(title="P3", content="...", subsystem="eclss")

    eclss_procs = memory.get_procedures_by_subsystem("eclss")
    assert len(eclss_procs) == 2


def test_learned_pattern(memory: MemoryStore):
    pattern = memory.learn_pattern(
        description="Increase CUSUM threshold during eclipse",
        context="eclipse transition",
        action="Set CUSUM k=0.7 during eclipse",
        confidence=0.6,
    )
    assert pattern.confidence == 0.6

    # Find applicable patterns
    applicable = memory.get_applicable_patterns("eclipse transition detected")
    assert len(applicable) >= 1

    # Record outcome
    memory.record_pattern_outcome(pattern.pattern_id, success=True)
    assert pattern.times_applied == 1
    assert pattern.success_rate == 1.0

    memory.record_pattern_outcome(pattern.pattern_id, success=False)
    assert pattern.times_applied == 2
    assert pattern.success_rate == 0.5


def test_summary(memory: MemoryStore):
    memory.push_working({"event": "test"})
    summary = memory.summary()
    assert summary["working_memory_items"] == 1
    assert summary["episodes"] == 0


async def test_episode_count():
    store = MemoryStore()
    assert store.get_episode_count() == 0
    await store.store_episode("test", "summary1", {"k": 1})
    await store.store_episode("test", "summary2", {"k": 2})
    assert store.get_episode_count() == 2


async def test_episode_recall_by_type():
    store = MemoryStore()
    await store.store_episode("anomaly", "Battery low", {})
    await store.store_episode("reasoning", "Query processed", {})
    await store.store_episode("anomaly", "CO2 high", {})

    anomalies = store.recall_episodes(event_type="anomaly")
    assert len(anomalies) == 2


def test_procedure_search_no_results():
    store = MemoryStore()
    store.add_procedure(title="Fire", content="Steps", category="emergency")
    results = store.search_procedures("nonexistent_keyword")
    assert len(results) == 0
