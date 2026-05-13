"""R43 — Apollo replay validator integration test.

Runs the full Apollo 11 mission profile through ARIA and compares
phase-by-phase against published flight values.  The test is
intentionally written so that **failures are informative**: a
divergence > tolerance does not assert "ARIA is broken" — it asserts
"the replay reveals a known modelling gap in this phase that should
either be fixed or have its tolerance raised explicitly with a
documented reason."
"""

from __future__ import annotations

import pytest

from aria.validation.apollo_replay import (
    ApolloReplayEvent, run_apollo_11_replay,
)


class TestApolloReplay:
    def test_report_has_expected_phases(self):
        report = run_apollo_11_replay()
        names = {e.name for e in report.events}
        for required in ("TLI", "LOI", "POWERED_DESCENT",
                         "POWERED_ASCENT", "TEI"):
            assert required in names, f"missing {required}"

    def test_tli_within_tight_tolerance(self):
        """TLI is the most-validated phase — Apollo flight ops cite
        ±0.5–1 % typical.  ARIA should clear 3 %."""
        report = run_apollo_11_replay()
        tli = next(e for e in report.events if e.name == "TLI")
        assert tli.passes, (
            f"TLI ARIA={tli.aria_dv_mps:.1f} m/s vs ref={tli.ref_dv_mps:.1f} "
            f"is {tli.pct_error:.2f}% off (tolerance {tli.tolerance_pct}%)"
        )

    def test_loi_within_tolerance(self):
        report = run_apollo_11_replay()
        loi = next(e for e in report.events if e.name == "LOI")
        assert loi.passes

    def test_powered_descent_within_tolerance(self):
        report = run_apollo_11_replay()
        pd = next(e for e in report.events if e.name == "POWERED_DESCENT")
        assert pd.passes

    def test_known_divergences_flagged_not_silent(self):
        """The replay must show all events, including divergent ones,
        rather than silently passing.  This guards against 'all green'
        false confidence."""
        report = run_apollo_11_replay()
        # The render_table must emit a max-drift line so a CI
        # operator can see the worst case at a glance.
        text = report.render_table()
        assert "max drift" in text
        assert "Honest reading" in text   # the disclaimer must be present

    def test_no_event_exceeds_its_own_tolerance(self):
        """Every event must fit within its own per-event tolerance (set
        in `_DEFAULT_TOLERANCE_PCT` per the source it's calibrated to).
        Small-Δv phases (rendezvous, DOI) carry larger percent
        tolerances because absolute precision dominates over %
        precision when the base value is small."""
        report = run_apollo_11_replay()
        offenders = [
            (e.name, e.pct_error, e.tolerance_pct)
            for e in report.events if not e.passes
        ]
        assert not offenders, (
            "events outside tolerance: "
            + ", ".join(f"{n}={p:.2f}% > {t}%" for n, p, t in offenders)
        )

    def test_big_burns_under_5_pct(self):
        """High-Δv phases (>500 m/s) must agree with reference within
        5 %.  This is the structural-bug guard the earlier 10 % bar
        was trying to express more carefully."""
        report = run_apollo_11_replay()
        big_phases = [e for e in report.events if e.ref_dv_mps > 500.0]
        for e in big_phases:
            assert e.pct_error < 5.0, (
                f"{e.name} drift {e.pct_error:.2f}% on a {e.ref_dv_mps:.0f} m/s "
                f"phase exceeds 5 % structural bar"
            )

    def test_zero_dv_phases_recorded(self):
        """Coast / surface-stay / EDL phases must appear with ref_dv = 0
        so the report acknowledges them rather than silently dropping."""
        report = run_apollo_11_replay()
        names = {e.name for e in report.events if e.ref_dv_mps == 0.0}
        assert "COAST_TO_MOON" in names
        assert "SURFACE_STAY" in names
        assert "ENTRY_DESCENT_LANDING" in names

    def test_every_event_has_citation(self):
        report = run_apollo_11_replay()
        for e in report.events:
            assert e.citation, f"phase {e.name} missing citation"


class TestEventArithmetic:
    def test_pct_error_zero_when_match(self):
        e = ApolloReplayEvent(
            name="x", ref_dv_mps=100.0, aria_dv_mps=100.0,
            tolerance_pct=1.0, citation="test",
        )
        assert e.pct_error == 0.0
        assert e.passes

    def test_passes_at_exactly_tolerance(self):
        e = ApolloReplayEvent(
            name="x", ref_dv_mps=100.0, aria_dv_mps=103.0,
            tolerance_pct=3.0, citation="test",
        )
        assert e.pct_error == 3.0
        assert e.passes

    def test_zero_ref_passes_only_if_aria_also_zero(self):
        ok = ApolloReplayEvent(
            name="x", ref_dv_mps=0.0, aria_dv_mps=0.0,
            tolerance_pct=1.0, citation="test",
        )
        bad = ApolloReplayEvent(
            name="y", ref_dv_mps=0.0, aria_dv_mps=5.0,
            tolerance_pct=1.0, citation="test",
        )
        assert ok.passes
        assert bad.passes is False
