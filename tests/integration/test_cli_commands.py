"""Tests for the AWS-style ARIA CLI."""

import subprocess
import sys

import pytest


def run_aria(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run aria CLI command and return result."""
    cmd = [sys.executable, "-m", "aria"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd="/home/ashutosh/Music/SpaceAi/aria-core")


class TestCLIHelp:
    def test_top_level_help(self) -> None:
        r = run_aria("--help")
        assert r.returncode == 0
        assert "sim" in r.stdout
        assert "system" in r.stdout
        assert "crew" in r.stdout

    def test_sim_help(self) -> None:
        r = run_aria("sim", "--help")
        assert r.returncode == 0
        assert "run" in r.stdout
        assert "montecarlo" in r.stdout

    def test_crew_help(self) -> None:
        r = run_aria("crew", "--help")
        assert r.returncode == 0
        assert "lifecycle" in r.stdout
        assert "genetics" in r.stdout

    def test_shield_help(self) -> None:
        r = run_aria("shield", "--help")
        assert r.returncode == 0
        assert "analyze" in r.stdout
        assert "erosion" in r.stdout

    def test_version(self) -> None:
        r = run_aria("--version")
        assert r.returncode == 0
        assert "1.0.0" in r.stdout


class TestCrewCommands:
    def test_genetics_text_output(self) -> None:
        r = run_aria("crew", "genetics", "--population", "10", "--years", "50")
        assert r.returncode == 0
        assert "Inbreeding" in r.stdout

    def test_genetics_json_output(self) -> None:
        r = run_aria("--output", "json", "crew", "genetics", "--population", "10", "--years", "50")
        assert r.returncode == 0
        assert '"inbreeding_F"' in r.stdout

    def test_ecosystem(self) -> None:
        r = run_aria("crew", "ecosystem", "--years", "50")
        assert r.returncode == 0
        assert "Element" in r.stdout


class TestSimCommands:
    def test_sim_help_shows_commands(self) -> None:
        r = run_aria("sim")
        assert r.returncode == 0
        assert "run" in r.stdout or "Simulation" in r.stdout


class TestDataCommands:
    def test_data_list_or_help(self) -> None:
        r = run_aria("data", "list")
        assert r.returncode == 0
        # Shows data info (either list or help)
        assert "data" in r.stdout.lower() or "Data" in r.stdout


class TestInvalidCommands:
    def test_unknown_service(self) -> None:
        r = run_aria("nonexistent")
        assert r.returncode != 0

    def test_no_args_shows_help(self) -> None:
        r = run_aria()
        assert r.returncode == 0
        assert "ARIA" in r.stdout
