"""Auto-mark slow and non-core tests based on file names.

Usage:
  pytest tests/                          # Run everything (4+ min)
  pytest tests/ -m "not slow"            # Skip 200-year sims (~2 min)
  pytest tests/ -m "not noncore"         # Skip social/governance/language
  pytest tests/ -m "not slow and not noncore"  # Core physics only (~90s)
"""
import pytest

# Files containing 200-year simulations or multi-agent scenarios
SLOW_FILES = {
    "test_generation_ship.py",
    "test_novel_inspired.py",
    "test_mining_mission.py",
    "test_mission_scenarios.py",
    "test_advanced_scenarios.py",
    "test_scenario_stress.py",
}

# Non-core: social systems, governance, language, colonization, novels
NONCORE_FILES = {
    "test_biology_social.py",
    "test_thermal_governance.py",
    "test_novel_scenarios.py",
    "test_novel_inspired.py",
    "test_crew_ecosystem.py",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        filename = item.fspath.basename
        if filename in SLOW_FILES:
            item.add_marker(pytest.mark.slow)
        if filename in NONCORE_FILES:
            item.add_marker(pytest.mark.noncore)
