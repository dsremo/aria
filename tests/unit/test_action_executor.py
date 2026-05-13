from __future__ import annotations
import pytest
from aria.cognitive.action_executor import (
    ActionIntent, parse_recommendation,
)


def test_parse_throttle_engine():
    intents = parse_recommendation("Recommendation: throttle_engine 0.6 and monitor.")
    assert len(intents) == 1
    assert intents[0].action == "throttle_engine"
    assert abs(intents[0].params["fraction"] - 0.6) < 1e-9


def test_parse_multiple_actions():
    text = """
    - throttle_engine 0.5
    - shed_load ECLSS
    - safe_mode
    """
    intents = parse_recommendation(text)
    actions = {i.action for i in intents}
    assert "throttle_engine" in actions
    assert "shed_load" in actions
    assert "safe_mode" in actions


def test_parse_no_action_empty_list():
    assert parse_recommendation("No action required.") == []


# test_executor_calls_registered_callback + test_executor_no_callback_fails_gracefully
# removed: ActionExecutor class deleted (Pass 3 F14.13 — zero production callers).


def test_maneuver_parser_picks_up_dv():
    intents = parse_recommendation("schedule maneuver TEI burn 890 m/s")
    assert any(i.action == "schedule_maneuver" for i in intents)
    i = next(x for x in intents if x.action == "schedule_maneuver")
    assert abs(i.params["dv_mps"] - 890) < 1e-6


def test_vent_tank_and_pressurize():
    intents = parse_recommendation("vent_tank H2 and pressurize_cabin 101 kPa")
    assert any(i.action == "vent_tank" and i.params["tank_id"] == "H2" for i in intents)
    assert any(i.action == "pressurize_cabin" and abs(i.params["kpa"] - 101) < 1 for i in intents)
