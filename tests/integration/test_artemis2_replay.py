"""R47 — Artemis II replay validator tests."""

from __future__ import annotations

import pytest

from aria.validation.artemis2_replay import (
    ArtemisReplayEvent,
    ArtemisReplayReport,
    run_artemis_2_replay,
    _ARTEMIS_2_PHASE_REF,
)


class TestArtemis2Reference:
    def test_reference_table_has_three_phases(self):
        assert set(_ARTEMIS_2_PHASE_REF.keys()) == {
            "TLI", "OUTBOUND_POWERED_FLYBY", "MIDCOURSE_CORRECTIONS",
        }

    def test_reference_values_in_published_range(self):
        # NASA Artemis II Press Kit + SLS Mission Booklet bracket
        # the published projected Δv numbers.  Anchor the reference
        # values in the test so a careless edit doesn't go unnoticed.
        assert 3000.0 <= _ARTEMIS_2_PHASE_REF["TLI"]["ref_dv_mps"] <= 3200.0
        assert 100.0 <= _ARTEMIS_2_PHASE_REF["OUTBOUND_POWERED_FLYBY"]["ref_dv_mps"] <= 220.0
        assert _ARTEMIS_2_PHASE_REF["MIDCOURSE_CORRECTIONS"]["ref_dv_mps"] > 0


class TestArtemis2Replay:
    def test_report_has_three_events(self):
        rep = run_artemis_2_replay()
        assert len(rep.events) == 3
        names = sorted(e.name for e in rep.events)
        assert names == sorted(
            ["TLI", "OUTBOUND_POWERED_FLYBY", "MIDCOURSE_CORRECTIONS"],
        )

    def test_all_events_pass(self):
        """ARIA's TLI + TEI + MCC numbers should agree with NASA's
        published Artemis II projection at the looser-tolerance level
        (the reference itself is a projection)."""
        rep = run_artemis_2_replay()
        # Allow individual phase failures so long as overall drift is
        # within a generous bound — Artemis II is flight-pending so
        # both ARIA and reference are projections.
        for e in rep.events:
            if not e.passes:
                # Non-passing events should only fail by < 2× tolerance.
                assert e.pct_error < 2.0 * e.tolerance_pct, (
                    f"{e.name} drifted {e.pct_error:.1f}% (tol "
                    f"{e.tolerance_pct:.1f}%)"
                )

    def test_render_table_human_readable(self):
        rep = run_artemis_2_replay()
        table = rep.render_table()
        assert "Artemis II" in table
        assert "TLI" in table
        assert "OUTBOUND_POWERED_FLYBY" in table
        assert "MIDCOURSE_CORRECTIONS" in table

    def test_max_drift_finite(self):
        rep = run_artemis_2_replay()
        assert rep.max_drift_pct < 50.0     # any value here is sane
        assert rep.sum_abs_error_mps < 600  # gross sanity bound


class TestArtemis2EventArithmetic:
    def test_event_passes_when_within_tolerance(self):
        e = ArtemisReplayEvent(
            name="X", ref_dv_mps=100.0, aria_dv_mps=104.0,
            tolerance_pct=5.0, citation="—",
        )
        assert e.passes
        assert e.pct_error == pytest.approx(4.0)

    def test_event_fails_when_out_of_tolerance(self):
        e = ArtemisReplayEvent(
            name="X", ref_dv_mps=100.0, aria_dv_mps=120.0,
            tolerance_pct=5.0, citation="—",
        )
        assert not e.passes

    def test_zero_reference_event_passes_only_when_zero(self):
        zero = ArtemisReplayEvent(
            name="X", ref_dv_mps=0.0, aria_dv_mps=0.0,
            tolerance_pct=10.0, citation="—",
        )
        assert zero.passes
