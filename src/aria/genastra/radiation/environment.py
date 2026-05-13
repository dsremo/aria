"""Radiation environment modeling.

Panel 2 (SpaceX Starshield) critique:
"Radiation is NOT binary. Real radiation damage is a function of:
(a) particle type, (b) energy spectrum, (c) dose rate, (d) LET, (e) shielding."

This module provides the RadiationEnvironment validation and physical models.
"""

from __future__ import annotations

from aria.genastra.core.exceptions import InvalidRadiationEnvironmentError
from aria.genastra.core.models import ParticleType, RadiationEnvironment, RadiationType


def validate_radiation_environment(env: RadiationEnvironment) -> list[str]:
    """Validate physical plausibility of radiation parameters.

    Returns list of warnings. Raises on physically impossible values.
    """
    warnings: list[str] = []

    if env.dose_mgy <= 0:
        raise InvalidRadiationEnvironmentError("Dose must be positive (milliGray)")

    # P0-E3 (Limoli): LET is the primary determinant of biological effectiveness for
    # HZE ions (e.g., Fe-56 at ~200 keV/μm). Making it optional for HZE silently
    # produces radiation vulnerability scores without the most critical parameter.
    # Reference: Cucinotta & Durante (2006) Lancet Oncol 7:431-441.
    if env.particle_type == ParticleType.HZE_ION and env.let_kev_per_um is None:
        raise InvalidRadiationEnvironmentError(
            "let_kev_per_um is required for HZE_ION particle type. "
            "LET is the primary determinant of relative biological effectiveness (RBE) "
            "for heavy ions. Typical values: Fe-56 ~150–200 keV/μm, Si-28 ~50 keV/μm, "
            "C-12 ~12 keV/μm. Provide measured or estimated LET before running analysis."
        )

    if env.dose_rate_mgy_per_day <= 0:
        raise InvalidRadiationEnvironmentError("Dose rate must be positive")

    # Physical plausibility checks
    if env.dose_rate_mgy_per_day > 1000:
        warnings.append(
            f"Dose rate {env.dose_rate_mgy_per_day} mGy/day is extremely high. "
            f"Acute SPE rates are typically 10-100 mGy/hr. Verify units."
        )

    if env.radiation_type == RadiationType.GCR and env.dose_rate_mgy_per_day > 5:
        warnings.append(
            f"GCR dose rate {env.dose_rate_mgy_per_day} mGy/day exceeds typical "
            f"GCR range (0.3-0.6 mGy/day in LEO, 0.5-1.0 in deep space). "
            f"Are you modeling an SPE event?"
        )

    if env.let_kev_per_um is not None:
        if env.let_kev_per_um < 0:
            raise InvalidRadiationEnvironmentError("LET must be non-negative")
        if env.let_kev_per_um > 1000:
            warnings.append(
                f"LET {env.let_kev_per_um} keV/μm is extremely high. "
                f"Fe-56 ions (most damaging GCR) have LET ~150 keV/μm."
            )

    if env.shielding_g_per_cm2 < 0:
        raise InvalidRadiationEnvironmentError("Shielding must be non-negative")

    if env.duration_days is not None:
        implied_dose = env.dose_rate_mgy_per_day * env.duration_days
        if abs(implied_dose - env.dose_mgy) / max(env.dose_mgy, 0.001) > 0.5:
            warnings.append(
                f"Dose ({env.dose_mgy} mGy) doesn't match rate × duration "
                f"({env.dose_rate_mgy_per_day} × {env.duration_days} = {implied_dose:.1f} mGy). "
                f"Verify parameters."
            )

    return warnings


# ── Standard radiation environments ────────────────────────────────

def iss_6_month() -> RadiationEnvironment:
    """Standard ISS 6-month mission radiation environment."""
    return RadiationEnvironment(
        radiation_type=RadiationType.MIXED,
        dose_mgy=90.0,         # ISS 6-month dose ~90 mGy (Cucinotta 2014 NASA/TP-2013-217375 §3)
        dose_rate_mgy_per_day=0.5,  # ~0.5 mGy/day ISS average (Cucinotta 2014)
        particle_type=ParticleType.MIXED,
        shielding_g_per_cm2=20.0,  # ESTIMATE — ISS wall shielding ~20 g/cm² (Cucinotta 2014)
        let_kev_per_um=None,
        duration_days=180.0,
    )


def mars_transit() -> RadiationEnvironment:
    """Mars transit (7-month cruise) radiation environment.

    Based on MSL/RAD measurements during Curiosity cruise.
    """
    return RadiationEnvironment(
        radiation_type=RadiationType.GCR,
        dose_mgy=160.0,              # MSL/RAD cruise: 1.84 mSv/day × 240 d (Zeitlin 2013 Science 340 1080)
        dose_rate_mgy_per_day=0.66,  # Zeitlin 2013 Science 340 1080: ~1.84 mSv/d ≈ 0.66 mGy/d behind shielding
        particle_type=ParticleType.MIXED,
        shielding_g_per_cm2=10.0,    # ESTIMATE — MSL spacecraft hull ~10 g/cm² (Zeitlin 2013)
        let_kev_per_um=None,
        duration_days=240.0,
    )


def spe_event() -> RadiationEnvironment:
    """Major Solar Particle Event (SPE) — acute exposure.

    Based on the August 1972 SPE (worst recorded).
    """
    return RadiationEnvironment(
        radiation_type=RadiationType.SPE,
        dose_mgy=2000.0,              # Aug 1972 SPE: ~2 Gy behind 10 g/cm² (Cucinotta 2006 §5)
        dose_rate_mgy_per_day=48000.0, # ~2 Gy in 1 h = ~48 Gy/day (Cucinotta & Durante 2006 Lancet Oncol 7 431)
        particle_type=ParticleType.PROTON,
        shielding_g_per_cm2=10.0,
        let_kev_per_um=0.5,           # ESTIMATE — proton LET ~0.5 keV/μm at 100 MeV (ICRP Pub.60)
        duration_days=0.042,          # ~1 hour event duration (Cucinotta 2006)
    )


def lunar_surface_1_year() -> RadiationEnvironment:
    """Lunar surface radiation — 1 year."""
    return RadiationEnvironment(
        radiation_type=RadiationType.GCR,
        dose_mgy=380.0,              # ESTIMATE — lunar surface ~380 mGy/yr (Cucinotta 2014; LRO/CRaTER: Schwadron 2014)
        dose_rate_mgy_per_day=1.04,  # ESTIMATE — ~1.04 mGy/day lunar surface (Schwadron 2014 Space Weather 12 622)
        particle_type=ParticleType.MIXED,
        shielding_g_per_cm2=5.0,    # ESTIMATE — spacesuit shielding ~5 g/cm² (Cucinotta 2014)
        let_kev_per_um=None,
        duration_days=365.0,
    )
