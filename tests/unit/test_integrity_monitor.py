"""R38 — Continuous Integrity Monitor (CIM) tests.

Covers acceptance §1.1:
  * Manifest expansion (security/ subtree included).
  * Runtime hasher detects tamper between sweeps.
  * Mismatch publishes ``aria.security.cim_mismatch`` and triggers the
    on_mismatch callback within the 5 s reaction budget.
  * Idempotent firing — callback called only once until acknowledge().
"""

from __future__ import annotations

import hashlib
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from aria.security import integrity_monitor as cim


# ── Fixture: synthetic protected tree + manifest ─────────────────────


def _make_tree(root: Path, files: Dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def _render_manifest(root: Path, files: Dict[str, str]) -> str:
    lines = [
        "manifest_version = 1",
        'created_at       = "2026-04-26"',
        'algorithm        = "sha256"',
        "",
    ]
    for rel in sorted(files):
        body = (root / rel).read_bytes()
        h = hashlib.sha256(body).hexdigest()
        lines.append(f'[files."{rel}"]')
        lines.append(f'sha256 = "{h}"')
        lines.append("")
    return "\n".join(lines)


@pytest.fixture
def synthetic_tree(tmp_path, monkeypatch):
    """Create a fake aria/ pkg root with two protected files.  Patch
    PROTECTED_SUBTREES so the CIM only walks our fake tree."""
    pkg = tmp_path / "aria_pkg"
    files = {
        "cognitive/engine.py": "x = 1\n",
        "security/audit.py": "y = 2\n",
    }
    _make_tree(pkg, files)
    manifest = tmp_path / "MANIFEST.toml"
    manifest.write_text(_render_manifest(pkg, files))

    # The CIM imports _enumerate_protected_files / _parse_boot_manifest
    # directly from aria.boot.verify; only the subtrees list and roots
    # need to be sandboxed for the duration of the test.
    monkeypatch.setattr(
        "aria.boot.verify.PROTECTED_SUBTREES",
        ("cognitive", "security"),
    )
    return pkg, manifest, files


# ── Tests ───────────────────────────────────────────────────────────


class TestSweep:
    def test_manifest_includes_security_subtree(self):
        """R38 §1.1 — security/ must be in PROTECTED_SUBTREES."""
        from aria.boot.verify import PROTECTED_SUBTREES
        assert "security" in PROTECTED_SUBTREES

    def test_clean_tree_no_callback(self, synthetic_tree):
        pkg, manifest, _ = synthetic_tree
        events: List[Tuple[str, Dict[str, Any]]] = []
        fired: List[Dict[str, Any]] = []
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: fired.append(r),
            publish_fn=lambda t, p: events.append((t, p)),
            manifest_path=manifest,
            pkg_root=pkg,
        )
        result = m.sweep_once()
        assert result is None
        assert events == []
        assert fired == []
        stats = m.stats()
        assert stats["sweeps"] == 1
        assert stats["fired"] is False

    def test_tamper_fires_callback_and_publishes(self, synthetic_tree):
        pkg, manifest, _ = synthetic_tree
        events: List[Tuple[str, Dict[str, Any]]] = []
        fired: List[Dict[str, Any]] = []
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: fired.append(r),
            publish_fn=lambda t, p: events.append((t, p)),
            manifest_path=manifest,
            pkg_root=pkg,
        )

        # Tamper: rewrite a protected file.
        (pkg / "cognitive/engine.py").write_text("x = 999  # tampered\n")

        report = m.sweep_once()
        assert report is not None
        assert report["mismatched_count"] == 1
        assert "cognitive/engine.py" in report["mismatched"]
        assert events and events[0][0] == "aria.security.cim_mismatch"
        assert fired and fired[0]["sample_path"] == "cognitive/engine.py"

    def test_callback_fires_only_once_per_arming(self, synthetic_tree):
        pkg, manifest, _ = synthetic_tree
        fired: List[Dict[str, Any]] = []
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: fired.append(r),
            publish_fn=lambda t, p: None,
            manifest_path=manifest,
            pkg_root=pkg,
        )
        (pkg / "cognitive/engine.py").write_text("tamper\n")
        m.sweep_once()
        m.sweep_once()
        m.sweep_once()
        assert len(fired) == 1, "callback must not spam"

    def test_acknowledge_re_arms(self, synthetic_tree):
        pkg, manifest, _ = synthetic_tree
        fired: List[Dict[str, Any]] = []
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: fired.append(r),
            publish_fn=lambda t, p: None,
            manifest_path=manifest,
            pkg_root=pkg,
        )
        (pkg / "cognitive/engine.py").write_text("tamper-1\n")
        m.sweep_once()
        m.acknowledge()
        (pkg / "cognitive/engine.py").write_text("tamper-2\n")
        m.sweep_once()
        assert len(fired) == 2

    def test_missing_file_detected(self, synthetic_tree):
        pkg, manifest, _ = synthetic_tree
        fired: List[Dict[str, Any]] = []
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: fired.append(r),
            publish_fn=lambda t, p: None,
            manifest_path=manifest,
            pkg_root=pkg,
        )
        (pkg / "security/audit.py").unlink()
        report = m.sweep_once()
        assert report is not None
        assert report["missing_count"] == 1
        assert "security/audit.py" in report["missing"]

    def test_no_manifest_is_not_a_failure(self, tmp_path):
        # Dev-tree path: monitor sweeps cleanly when no manifest exists.
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: None,
            publish_fn=lambda t, p: None,
            manifest_path=tmp_path / "does_not_exist.toml",
            pkg_root=tmp_path,
        )
        assert m.sweep_once() is None
        assert m.stats()["sweeps"] == 1


class TestReactionBudget:
    def test_callback_returns_under_budget(self, synthetic_tree):
        """The mismatch path must not block longer than the 5 s budget
        (R38 §1.1)."""
        pkg, manifest, _ = synthetic_tree
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: None,
            publish_fn=lambda t, p: None,
            manifest_path=manifest,
            pkg_root=pkg,
        )
        (pkg / "cognitive/engine.py").write_text("tamper\n")
        t0 = time.monotonic()
        m.sweep_once()
        assert (time.monotonic() - t0) < cim.MISMATCH_REACTION_BUDGET_S


class TestThreadedRun:
    def test_thread_lifecycle(self, synthetic_tree):
        pkg, manifest, _ = synthetic_tree
        ev = threading.Event()
        m = cim.IntegrityMonitor(
            on_mismatch=lambda r: ev.set(),
            publish_fn=lambda t, p: None,
            period_s=5.0,            # clamped down to 5 s by ctor floor
            manifest_path=manifest,
            pkg_root=pkg,
        )
        # Tamper before start so the very first sweep fires.
        (pkg / "security/audit.py").write_text("tamper\n")
        m.start()
        try:
            assert ev.wait(timeout=10.0), "CIM never fired in 10 s"
        finally:
            m.stop()


class TestSingleton:
    def test_start_then_stop(self, synthetic_tree, monkeypatch):
        pkg, manifest, _ = synthetic_tree
        # Force the singleton helpers to use our sandboxed paths by
        # patching the defaults the constructor would otherwise pick.
        monkeypatch.setattr(
            "aria.security.integrity_monitor._default_manifest_path",
            lambda: manifest,
        )
        monkeypatch.setattr(
            "aria.security.integrity_monitor._aria_pkg_root",
            lambda: pkg,
        )
        cim.reset_for_test()
        try:
            mon = cim.start_integrity_monitor(
                on_mismatch=lambda r: None,
                publish_fn=lambda t, p: None,
                period_s=5.0,
            )
            assert cim.get_integrity_monitor() is mon
            # Idempotent: a second start returns the same instance.
            mon2 = cim.start_integrity_monitor(
                on_mismatch=lambda r: None,
            )
            assert mon is mon2
        finally:
            cim.reset_for_test()
        assert cim.get_integrity_monitor() is None
