"""Constants table for Pod A1 (§5 of docs/pods/A1_ephemeris.md).

Every value carries a published citation in an inline comment per
`aria-core/CLAUDE.md`. No `ESTIMATE` markers in this file — every row
has a primary source.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────
#  Fundamental constants
# ──────────────────────────────────────────────────────────────────────

# Gravitational constant, CODATA 2018 (Tiesinga 2021 Rev. Mod. Phys. 93
# 025010, DOI 10.1103/RevModPhys.93.025010). Relative uncertainty 2.2e-5.
GRAVITATIONAL_CONSTANT: float = 6.67430e-11  # m³ kg⁻¹ s⁻²

# Speed of light in vacuum (SI 2019 base-unit redefinition: exact).
SPEED_OF_LIGHT_M_S: float = 2.99792458e8  # m s⁻¹ (exact)

# Astronomical unit, IAU 2012 Resolution B2 (exact by definition).
AU_M: float = 1.49597870700e11  # m (exact)

# Light year = c × 1 Julian year of 365.25 days (IAU convention).
JULIAN_YEAR_S: float = 365.25 * 86400.0  # exact
LIGHT_YEAR_M: float = SPEED_OF_LIGHT_M_S * JULIAN_YEAR_S  # 9.4607304725808e15 m


# ──────────────────────────────────────────────────────────────────────
#  Solar-system gravitational parameters (GM = G·M)
#  These are the primary quantities delivered by modern ephemerides;
#  individual masses have larger uncertainty than GM values.
# ──────────────────────────────────────────────────────────────────────

# Sun GM — JPL DE440 (Park 2021 AJ 161 105 DOI 10.3847/1538-3881/abd414).
GM_SUN_M3_S2: float = 1.32712440041939e20  # m³ s⁻² (DE440)

# Earth GM — WGS-84 (NIMA TR 8350.2, 3rd ed, 2000).
GM_EARTH_M3_S2: float = 3.986004418e14  # m³ s⁻² (WGS-84)

# Moon GM — JPL DE440 (Park 2021 Table 8).
GM_MOON_M3_S2: float = 4.902800066e12  # m³ s⁻² (DE440)

# Mars GM — JPL DE440 (Park 2021 Table 8).
GM_MARS_M3_S2: float = 4.2828375214e13  # m³ s⁻² (DE440)

# Jupiter GM — Juno gravity science (Iess 2018 Nature 555 220
# DOI 10.1038/nature25776). Dominated by Jupiter's C_20/J2; the GM itself
# is known to 10 ppm.
GM_JUPITER_M3_S2: float = 1.26686534e17  # m³ s⁻² (Juno)

# Saturn GM — Cassini gravity (Iess 2019 Science 364 aat2965
# DOI 10.1126/science.aat2965).
GM_SATURN_M3_S2: float = 3.7931187e16  # m³ s⁻² (Cassini)


# ──────────────────────────────────────────────────────────────────────
#  Mean body radii (IAU 2015 Resolution B3 nominal values)
# ──────────────────────────────────────────────────────────────────────

R_SUN_M: float = 6.957e8  # m  (IAU 2015 B3 nominal solar radius)
R_EARTH_M: float = 6.3781e6  # m  (IAU 2015 B3 nominal Earth equatorial)
R_JUPITER_M: float = 7.1492e7  # m  (IAU 2015 B3 nominal Jupiter equatorial)


# ──────────────────────────────────────────────────────────────────────
#  Zonal gravity (J2) coefficients for close-approach corrections
# ──────────────────────────────────────────────────────────────────────

# Earth J2 — EGM2008 (Pavlis 2012 J. Geophys. Res. 117 B04406
# DOI 10.1029/2011JB008916). Normalized C_{20} = -4.8416531e-4;
# unnormalized J2 = -√5 · C_{20} = 1.082626e-3.
J2_EARTH: float = 1.082626e-3  # dimensionless (EGM2008)

# Jupiter J2 — Juno gravity science (Iess 2018 Nature 555 220).
J2_JUPITER: float = 1.4696e-2  # dimensionless (Juno)


# ──────────────────────────────────────────────────────────────────────
#  Nearby-star gravitational parameters
#  These convert the cataloged stellar mass to a GM for A1's force model.
# ──────────────────────────────────────────────────────────────────────

# α Centauri A — Kervella 2016 A&A 594 A107
# DOI 10.1051/0004-6361/201629201. Mass 1.1055 M_sun.
GM_ALPHA_CEN_A_M3_S2: float = 1.1055 * GM_SUN_M3_S2  # Kervella 2016

# α Centauri B — Kervella 2016.
GM_ALPHA_CEN_B_M3_S2: float = 0.9373 * GM_SUN_M3_S2  # Kervella 2016

# Proxima Centauri — Mann 2019 ApJ 871 63 DOI 10.3847/1538-4357/aaf3bc.
GM_PROXIMA_M3_S2: float = 0.1221 * GM_SUN_M3_S2  # Mann 2019
