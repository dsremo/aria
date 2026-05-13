"""Tests for V3-W4: mission phase gating for detection suppression.

Validates:
 1. Default phase for unknown satellite is NOMINAL (detection active)
 2. INTEGRATION/LAUNCH/COMMISSIONING/NOMINAL/END_OF_LIFE enum values
 3. set_phase records entered_at and transitions cleanly
 4. Commissioning suppresses detection
 5. Other phases (integration/launch/nominal/eol) keep detection active
 6. Auto-transition from COMMISSIONING → NOMINAL after default 48 h
 7. Custom commissioning_duration_h honoured
 8. Before commissioning_duration_h elapsed, detection stays suppressed
 9. iter_states yields every registered satellite
10. Singleton helpers get_registry / reset_registry
"""

from __future__ import annotations

import pytest

from aria.dsremo.detection.mission_phase import (
    DEFAULT_COMMISSIONING_DURATION_H,
    MissionPhase,
    MissionPhaseRegistry,
    PhaseState,
    get_registry,
    reset_registry,
)


class TestEnum:

    def test_phase_values(self):
        assert MissionPhase.INTEGRATION   == "integration"
        assert MissionPhase.LAUNCH        == "launch"
        assert MissionPhase.COMMISSIONING == "commissioning"
        assert MissionPhase.NOMINAL       == "nominal"
        assert MissionPhase.END_OF_LIFE   == "end_of_life"


class TestRegistry:

    def test_default_is_nominal(self):
        reg = MissionPhaseRegistry()
        st = reg.get("SAT-A")
        assert st.phase == MissionPhase.NOMINAL
        assert isinstance(st, PhaseState)

    def test_set_phase_records_entered_at(self):
        reg = MissionPhaseRegistry()
        st = reg.set_phase("SAT-A", MissionPhase.COMMISSIONING, epoch=1000.0)
        assert st.phase == MissionPhase.COMMISSIONING
        assert st.entered_at == 1000.0


class TestDetectionGate:

    def test_commissioning_suppresses_detection(self):
        reg = MissionPhaseRegistry()
        reg.set_phase("SAT", MissionPhase.COMMISSIONING, epoch=1000.0)
        # 10 seconds later — still in commissioning.
        assert not reg.is_detection_active("SAT", now_epoch=1010.0)

    def test_nominal_allows_detection(self):
        reg = MissionPhaseRegistry()
        reg.set_phase("SAT", MissionPhase.NOMINAL, epoch=1000.0)
        assert reg.is_detection_active("SAT", now_epoch=1010.0)

    def test_other_phases_allow_detection(self):
        reg = MissionPhaseRegistry()
        for phase in (MissionPhase.INTEGRATION, MissionPhase.LAUNCH, MissionPhase.END_OF_LIFE):
            reg.set_phase("SAT", phase, epoch=1000.0)
            assert reg.is_detection_active("SAT", now_epoch=1010.0)

    def test_unknown_satellite_default_allows_detection(self):
        reg = MissionPhaseRegistry()
        assert reg.is_detection_active("NEW-SAT")


class TestAutoTransition:

    def test_auto_transition_after_default_duration(self):
        reg = MissionPhaseRegistry()
        reg.set_phase("SAT", MissionPhase.COMMISSIONING, epoch=0.0)
        # Just past the default duration in seconds.
        later = DEFAULT_COMMISSIONING_DURATION_H * 3600.0 + 1.0
        assert reg.is_detection_active("SAT", now_epoch=later)
        # The registry mutated in place → phase is now NOMINAL.
        assert reg.get("SAT").phase == MissionPhase.NOMINAL

    def test_custom_duration_honoured(self):
        reg = MissionPhaseRegistry()
        # 1 hour window.
        reg.set_phase("SAT", MissionPhase.COMMISSIONING, epoch=0.0, commissioning_duration_h=1.0)
        assert not reg.is_detection_active("SAT", now_epoch=1800.0)  # 30 min → still suppressed
        assert reg.is_detection_active("SAT", now_epoch=3700.0)      # >1 h → active, auto-transitioned

    def test_within_duration_still_suppressed(self):
        reg = MissionPhaseRegistry()
        reg.set_phase("SAT", MissionPhase.COMMISSIONING, epoch=0.0, commissioning_duration_h=48.0)
        # 24 h in — still suppressed.
        assert not reg.is_detection_active("SAT", now_epoch=24 * 3600.0)


class TestIterAndSingleton:

    def test_iter_states_yields_every_satellite(self):
        reg = MissionPhaseRegistry()
        reg.set_phase("A", MissionPhase.NOMINAL, epoch=1.0)
        reg.set_phase("B", MissionPhase.COMMISSIONING, epoch=1.0)
        ids = [s.satellite_id for s in reg.iter_states()]
        assert set(ids) == {"A", "B"}

    def test_singleton_get_reset(self):
        reset_registry()
        try:
            a = get_registry()
            b = get_registry()
            assert a is b
            a.set_phase("X", MissionPhase.COMMISSIONING)
            # Reset produces a fresh registry.
            reset_registry()
            c = get_registry()
            assert c is not a
            assert c.get("X").phase == MissionPhase.NOMINAL
        finally:
            reset_registry()


class TestDetectionCycleGate:
    """Verify run_detection_cycle honours the mission-phase gate."""

    @pytest.mark.asyncio
    async def test_commissioning_skips_detection(self, monkeypatch):
        import aria.dsremo.detection.detector as det_mod
        from aria.dsremo.detection import mission_phase as mp_mod

        reset_registry()
        try:
            mp_mod.get_registry().set_phase(
                "SAT-CX", MissionPhase.COMMISSIONING,
                commissioning_duration_h=48.0,
            )

            # Poison get_latest_values so detection WOULD fail if reached —
            # this verifies the gate returns early.
            async def _explode(*_a, **_k):
                raise RuntimeError("should not be called during commissioning")
            monkeypatch.setattr(det_mod.queries, "get_latest_values", _explode)

            result = await det_mod.run_detection_cycle("SAT-CX")
            assert result == []
        finally:
            reset_registry()
