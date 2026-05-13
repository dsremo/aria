"""Tests for the process-wide AI decision log."""

from __future__ import annotations

import pytest

from aria.cognitive.decision_log import (
    DecisionEntry, DecisionLog, get_decision_log,
)


def test_append_and_recent():
    log = DecisionLog(capacity=5)
    assert len(log) == 0
    log.append(source="advisor", question="q1", response="r1", severity="INFO")
    log.append(source="agent",  question="q2", response="r2", agent="power",
               tools_used=["get_power_budget"], steps=3)
    assert len(log) == 2

    recent = log.recent(limit=10)
    assert len(recent) == 2
    assert recent[0].source == "advisor"
    assert recent[1].agent == "power"
    assert recent[1].tools_used == ["get_power_budget"]


def test_monotonic_ids():
    log = DecisionLog(capacity=10)
    ids = []
    for i in range(4):
        e = log.append(source="advisor", question=f"q{i}", response="ok")
        ids.append(e.id)
    assert ids == sorted(ids)
    assert ids[0] < ids[1] < ids[2] < ids[3]


def test_since_id_polling():
    log = DecisionLog(capacity=100)
    for i in range(10):
        log.append(source="advisor", question=f"q{i}", response="ok")

    first_batch = log.recent(limit=5, since_id=0)
    last_id = first_batch[-1].id
    # Nothing new — should be empty
    assert log.recent(limit=5, since_id=log.recent(limit=100)[-1].id) == []
    # After adding one more, only the new one returns
    log.append(source="advisor", question="q_new", response="ok")
    newer = log.recent(limit=5, since_id=last_id)
    assert len(newer) == 1
    assert newer[0].question == "q_new"


def test_capacity_ring():
    log = DecisionLog(capacity=3)
    for i in range(7):
        log.append(source="advisor", question=f"q{i}", response="ok")
    assert len(log) == 3
    recent = log.recent(limit=10)
    # Only the last 3 remain
    assert [e.question for e in recent] == ["q4", "q5", "q6"]


def test_entry_to_dict_stable():
    e = DecisionEntry(id=1, ts=123.0, source="agent",
                      question="q", response="r", tools_used=["x", "y"],
                      steps=2, severity="WARNING", backend="llm")
    d = e.to_dict()
    assert d["id"] == 1
    assert d["tools_used"] == ["x", "y"]
    # Mutating the returned dict's list must not mutate the entry
    d["tools_used"].append("z")
    assert e.tools_used == ["x", "y"]


def test_global_singleton_is_same_instance():
    a = get_decision_log()
    b = get_decision_log()
    assert a is b
