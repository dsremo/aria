"""Gravitational redshift — photon frequency between two potentials
(§4.5 of docs/pods/A2_tidal_tensor.md).

A photon emitted at point A (potential Φ_A) and received at point B
(potential Φ_B) has frequency ratio

    ν_B / ν_A = √( (1 + 2Φ_A/c²) / (1 + 2Φ_B/c²) )
             ≈ 1 + (Φ_A − Φ_B) / c²                     [dimensionless]

(Pound & Rebka 1960 PRL 4 337 DOI 10.1103/PhysRevLett.4.337 — first
terrestrial test). The sign convention: if Φ_A < Φ_B (A is deeper in
the well) then ν_B / ν_A < 1 — the photon is **red-shifted** as it
climbs out.

For a uniform gravitational field over a short vertical path `h`, the
shift reduces to

    Δν/ν = g h / c²                                     [dimensionless]

which is the classical Pound-Rebka 1960 formula (Δν/ν = 2.46e-15 for
g = 9.81 m/s² and h = 22.5 m — the Harvard tower experiment).

Modern precision: Chou 2010 Science 329 1630
(DOI 10.1126/science.1192720) measured the shift across a 33 cm height
difference with Al⁺ optical clocks, getting a fractional shift of
~3.6e-17 — the floor of what atomic timekeeping can resolve today.
"""

from __future__ import annotations

# Exact speed of light (SI 2019).
SPEED_OF_LIGHT_M_S: float = 2.99792458e8


def gravitational_redshift(
    phi_emit_m2_s2: float, phi_receive_m2_s2: float
) -> float:
    """Fractional frequency shift `Δν/ν = (Φ_emit − Φ_recv) / c²`.

    Returns:
        Dimensionless fractional frequency shift. Negative → redshift
        (photon climbed out of the well). Positive → blueshift.

    Note: the linearised form is used; valid whenever
    |Φ|/c² ≪ 1 (true for all solar-system potentials).
    """
    return (phi_emit_m2_s2 - phi_receive_m2_s2) / (SPEED_OF_LIGHT_M_S**2)


def pound_rebka_shift(g_m_s2: float, height_m: float) -> float:
    """Pound-Rebka shift `Δν/ν = g h / c²` for a uniform vertical field.

    Args:
        g_m_s2: gravitational field strength (m/s²). Positive.
        height_m: signed vertical path length from emitter to receiver
            (m). Positive means the receiver is above the emitter —
            the photon climbs the well and is redshifted, so the
            returned value is negative (the magnitude is the
            Pound-Rebka number).

    Returns:
        Signed ``Δν/ν`` (dimensionless).

    Canonical test: Pound & Rebka 1960 used g = 9.81 m/s² and
    h = 22.5 m (the Harvard Jefferson Physical Lab tower), giving
    Δν/ν = −2.46e-15 (photon climbing → redshift).
    """
    if g_m_s2 < 0.0:
        raise ValueError("g_m_s2 must be non-negative")
    # A photon traveling UP (positive h) is climbing the well
    # (Φ increases with h); the received ν is lower than emitted ν,
    # so Δν/ν is negative.
    return -g_m_s2 * height_m / (SPEED_OF_LIGHT_M_S**2)
