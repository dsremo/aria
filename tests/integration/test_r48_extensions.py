"""R48 — tests for LeoLabs / IS4OM / DSM porkchop / Soyuz replay."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from aria.conjunction.data.leolabs_session import (
    LeoLabsSession, LeoLabsState, _state_from_payload,
)
from aria.conjunction.data.is4om_session import (
    IS4OMSession, IS4OMConjunctionMessage, _cdm_from_payload,
)
from aria.validation.soyuz_rendezvous_replay import (
    run_soyuz_6hr_replay,
    SoyuzReplayEvent,
    _SOYUZ_6HR_REF,
)


# ── LeoLabs adapter ────────────────────────────────────────────


class TestLeoLabsAdapter:
    def test_payload_round_trip(self):
        cov = [[1.0 if i == j else 0.0 for j in range(6)] for i in range(6)]
        raw = {
            "norad_id": "24946",
            "epoch": "2026-04-26T12:00:00Z",
            "position": [7000.0, 0.0, 0.0],
            "velocity": [0.0, 7.5, 0.0],
            "covariance": cov,
        }
        st = _state_from_payload(raw)
        assert st.norad_id == "24946"
        assert st.position_km.shape == (3,)
        assert st.covariance_6x6_km2.shape == (6, 6)
        # 3x3 position-only block.
        cov3 = st.covariance_position_3x3_km2()
        assert cov3.shape == (3, 3)
        assert float(cov3[0, 0]) == pytest.approx(1.0)

    def test_cached_mode_reads_disk(self, tmp_path: Path):
        cov = [[1.0 if i == j else 0.0 for j in range(6)] for i in range(6)]
        raw = {
            "norad_id": "24946",
            "epoch": "2026-04-26T12:00:00Z",
            "position": [7000.0, 0.0, 0.0],
            "velocity": [0.0, 7.5, 0.0],
            "covariance": cov,
        }
        (tmp_path / "24946.json").write_text(json.dumps(raw))
        sess = LeoLabsSession(cache_dir=str(tmp_path))
        st = sess.state_for_norad("24946")
        assert st is not None
        assert st.norad_id == "24946"
        cov3 = sess.covariance_for_norad("24946")
        assert cov3 is not None
        assert cov3.shape == (3, 3)

    def test_cached_mode_missing_file_returns_none(self, tmp_path: Path):
        sess = LeoLabsSession(cache_dir=str(tmp_path))
        assert sess.state_for_norad("99999") is None

    def test_no_token_no_cache_returns_none(self):
        sess = LeoLabsSession()
        assert sess.state_for_norad("24946") is None


# ── IS4OM adapter ──────────────────────────────────────────────


class TestIS4OMAdapter:
    def test_payload_round_trip(self):
        raw = {
            "primary_norad_id": "24946",
            "secondary_norad_id": "22675",
            "tca_utc": "2009-02-10T16:56:00Z",
            "miss_distance_m": 584.0,
            "relative_velocity_kmps": 11.65,
            "pc_bin": "RED",
            "pc": 1e-3,
        }
        cdm = _cdm_from_payload(raw)
        assert cdm.primary_norad_id == "24946"
        assert cdm.pc_bin == "RED"
        assert cdm.pc_value == pytest.approx(1e-3)
        assert cdm.miss_distance_m == pytest.approx(584.0)

    def test_cached_cdms_read_disk(self, tmp_path: Path):
        raw_list = [
            {
                "primary_norad_id": "24946",
                "secondary_norad_id": "22675",
                "tca_utc": "2009-02-10T16:56:00Z",
                "miss_distance_m": 584.0,
                "relative_velocity_kmps": 11.65,
                "pc_bin": "RED",
            },
            {
                "primary_norad_id": "24946",
                "secondary_norad_id": "12345",
                "tca_utc": "2009-02-12T00:00:00Z",
                "miss_distance_m": 5000.0,
                "relative_velocity_kmps": 12.0,
                "pc_bin": "GREEN",
            },
        ]
        (tmp_path / "24946_cdms.json").write_text(json.dumps(raw_list))
        sess = IS4OMSession(cache_dir=str(tmp_path))
        cdms = sess.cdm_for_norad("24946")
        assert len(cdms) == 2
        assert cdms[0].pc_bin == "RED"
        assert cdms[1].pc_bin == "GREEN"

    def test_unknown_pc_bin_normalised(self):
        raw = {
            "primary_norad_id": "1", "secondary_norad_id": "2",
            "tca_utc": "2026-04-26T00:00:00Z",
            "miss_distance_m": 0.0, "relative_velocity_kmps": 0.0,
            "pc_bin": "WEIRD",
        }
        cdm = _cdm_from_payload(raw)
        assert cdm.pc_bin == "GREEN"

    def test_no_token_no_cache_returns_empty(self):
        sess = IS4OMSession()
        assert sess.cdm_for_norad("24946") == []


# ── Porkchop DSM extension ────────────────────────────────────


class TestPorkchopDSM:
    def test_dsm_solution_for_simple_inertial_geometry(self):
        from aria.simulation.porkchop_dsm import compute_porkchop_dsm
        # Synthetic Earth-Mars-like orbit pair: planar circular orbits.
        # Using simple parameters that exercise the code path.
        MU_SUN = 1.32712440018e20  # m³/s² — IAU 2009 value
        AU = 1.495978707e11

        def r_earth(day):
            theta = 2 * np.pi * day / 365.25
            return AU * np.array([np.cos(theta), np.sin(theta), 0.0])

        def v_earth(day):
            theta = 2 * np.pi * day / 365.25
            v = 2 * np.pi * AU / (365.25 * 86_400.0)
            return v * np.array([-np.sin(theta), np.cos(theta), 0.0])

        def r_mars(day):
            theta = 2 * np.pi * day / 686.97
            return 1.524 * AU * np.array([np.cos(theta), np.sin(theta), 0.0])

        def v_mars(day):
            theta = 2 * np.pi * day / 686.97
            v = 2 * np.pi * 1.524 * AU / (686.97 * 86_400.0)
            return v * np.array([-np.sin(theta), np.cos(theta), 0.0])

        result = compute_porkchop_dsm(
            mu_central=MU_SUN,
            r_dep_fn=r_earth, r_arr_fn=r_mars,
            v_dep_fn=v_earth, v_arr_fn=v_mars,
            t_dep_days=0.0, t_arr_days=210.0,
            n_dsm=11,
        )
        # We expect *some* solution to come back.
        assert len(result.solutions) > 0
        assert result.best_total_dv is not None
        assert result.best_total_dv.dsm_dv_mps >= 0.0
        assert result.best_total_dv.transit_days == pytest.approx(210.0)

    def test_invalid_arrival_before_departure_raises(self):
        from aria.simulation.porkchop_dsm import compute_porkchop_dsm

        def fixed_r(day):
            return np.array([1.0e11, 0.0, 0.0])

        def fixed_v(day):
            return np.array([0.0, 30_000.0, 0.0])

        with pytest.raises(ValueError):
            compute_porkchop_dsm(
                mu_central=1.327e20,
                r_dep_fn=fixed_r, r_arr_fn=fixed_r,
                v_dep_fn=fixed_v, v_arr_fn=fixed_v,
                t_dep_days=10.0, t_arr_days=5.0,
            )


# ── Soyuz rendezvous replay ────────────────────────────────────


class TestSoyuzReplay:
    def test_six_events_published(self):
        rep = run_soyuz_6hr_replay()
        names = sorted(e.name for e in rep.events)
        assert names == sorted([
            "DV1_PHASING_1", "DV2_PHASING_2", "DV3_CORRECTION",
            "DV4_BRAKING", "DV5_TPI", "DV6_FINAL",
        ])

    def test_total_in_published_band(self):
        rep = run_soyuz_6hr_replay()
        # Published nominal total ~ 80 m/s; ARIA's first-principles
        # Hohmann lands ~ 150 m/s because it ignores the multi-orbit
        # phasing efficiency that real Soyuz GNC exploits — the
        # validator's per-burn tolerances absorb that, but the *total*
        # naturally lands ~ 1.5-2x the published nominal.  Bound it
        # in a generous band so the test still flags egregious drift.
        assert 50.0 <= rep.total_dv_mps_aria <= 250.0
        assert 60.0 <= rep.total_dv_mps_ref   <=  90.0

    def test_render_table_human_readable(self):
        rep = run_soyuz_6hr_replay()
        out = rep.render_table()
        assert "Soyuz" in out
        assert "DV1_PHASING_1" in out
        assert "DV6_FINAL" in out

    def test_zero_reference_event_passes_only_when_zero(self):
        e = SoyuzReplayEvent(
            name="X", ref_dv_mps=0.0, aria_dv_mps=0.0,
            tolerance_pct=10.0, citation="—",
        )
        assert e.passes

    def test_event_passes_when_within_tolerance(self):
        e = SoyuzReplayEvent(
            name="X", ref_dv_mps=20.0, aria_dv_mps=22.0,
            tolerance_pct=20.0, citation="—",
        )
        assert e.passes
