"""Tests for domain models and validation."""

from __future__ import annotations

import pytest

from aria.genastra.core.models import (
    DetectionSignificance,
    DoseResponseModel,
    JobStatus,
    ParticleType,
    ProteinSequence,
    RadiationEnvironment,
    RadiationType,
)


class TestProteinSequence:
    def test_valid_sequence(self, sample_sequence: str) -> None:
        ps = ProteinSequence(sequence=sample_sequence)
        assert ps.length == len(sample_sequence)
        assert len(ps.sequence_hash) == 64  # SHA-256 hex

    def test_hash_deterministic(self, sample_sequence: str) -> None:
        ps1 = ProteinSequence(sequence=sample_sequence)
        ps2 = ProteinSequence(sequence=sample_sequence)
        assert ps1.sequence_hash == ps2.sequence_hash

    def test_different_sequences_different_hashes(self) -> None:
        ps1 = ProteinSequence(sequence="MKTL")
        ps2 = ProteinSequence(sequence="MKTV")
        assert ps1.sequence_hash != ps2.sequence_hash

    def test_frozen(self, sample_sequence: str) -> None:
        ps = ProteinSequence(sequence=sample_sequence)
        with pytest.raises(AttributeError):
            ps.sequence = "CHANGED"  # type: ignore[misc]


class TestRadiationEnvironment:
    def test_valid_gcr(self) -> None:
        env = RadiationEnvironment(
            radiation_type=RadiationType.GCR,
            dose_mgy=90.0,
            dose_rate_mgy_per_day=0.5,
            particle_type=ParticleType.MIXED,
        )
        assert env.dose_mgy == 90.0

    def test_valid_spe(self) -> None:
        env = RadiationEnvironment(
            radiation_type=RadiationType.SPE,
            dose_mgy=2000.0,
            dose_rate_mgy_per_day=48000.0,
            particle_type=ParticleType.PROTON,
            let_kev_per_um=0.5,
        )
        assert env.radiation_type == RadiationType.SPE

    def test_default_shielding(self) -> None:
        env = RadiationEnvironment(
            radiation_type=RadiationType.GCR,
            dose_mgy=90.0,
            dose_rate_mgy_per_day=0.5,
            particle_type=ParticleType.MIXED,
        )
        assert env.shielding_g_per_cm2 == 20.0


class TestEnums:
    def test_job_status_values(self) -> None:
        assert JobStatus.PENDING == "pending"
        assert JobStatus.COMPLETED == "completed"

    def test_detection_significance_values(self) -> None:
        assert DetectionSignificance.DECISIVE == "decisive"

    def test_dose_response_model(self) -> None:
        assert DoseResponseModel.LNT == "lnt"
        assert DoseResponseModel.BOTH == "both"
