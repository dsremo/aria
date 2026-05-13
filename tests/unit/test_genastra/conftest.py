"""Test fixtures for GenAstra."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_sequence() -> str:
    """A short valid protein sequence (insulin B chain)."""
    return "FVNQHLCGSHLVEALYLVCGERGFFYTPKT"


@pytest.fixture
def long_sequence() -> str:
    """A longer protein sequence for stress testing."""
    return "MKTLLILAVVAAALA" * 100  # 1500 residues


@pytest.fixture
def invalid_sequence() -> str:
    """A sequence with invalid characters."""
    return "MKTL123XYZNOTAPROTEIN!!!"
