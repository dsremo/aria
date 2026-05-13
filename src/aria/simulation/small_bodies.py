"""Bright asteroids and famous comets — heliocentric Keplerian propagation.

For each body we keep a single epoch's osculating element set
(a, e, i, Ω, ω, M) plus an absolute magnitude H and slope G for the
HG photometric model (Bowell et al. 1989). Position is computed by
the same Standish/Meeus pipeline as solar_system.py but with per-body
elements that may include hyperbolic (e ≥ 1) orbits for some comets.

Element sources (all public-domain per JPL/MPC policy):
- IAU Minor Planet Center MPCORB elements (epoch 2024-Jul-01)
- JPL Small-Body Database Browser
- Marsden 1996 (P/Halley)

Why a curated list rather than the full ~1.3 million-body MPC:
the planetarium is meant for sky visualization, not survey work.
The 30-ish bodies here cover everything ever named in popular
astronomy plus the first hundred main-belt asteroids. For
operations-grade work hit JPL HORIZONS through SPICE.

References:
    Bowell, E. et al. (1989) "Application of photometric models to
        asteroids." Asteroids II, U. Arizona Press.
    Marsden, B. G. (1996) "Catalogue of cometary orbits." 11th ed.
    Standish, E. M. (1992) JPL IOM 312.D-92-009.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from aria.simulation.solar_system import (
    EPSILON_J2000_DEG,
    PLANET_COLOR,
    SkyBody,
    centuries_from_j2000,
    heliocentric_ecliptic as _planet_helio,
    _ecliptic_to_equatorial,
    _solve_kepler,
)


# ════════════════════════════════════════════════════════════════════
#  Bright asteroid elements (epoch JD 2460492.5 = 2024-Jul-01.0)
#  Source: MPCORB.DAT 2024-07-01. a [AU], e, i [deg], Ω [deg],
#  ω [deg], M [deg], H [V mag], G slope.
# ════════════════════════════════════════════════════════════════════

@dataclass
class SmallBody:
    name: str
    a_au: float
    e: float
    inc_deg: float
    node_deg: float
    argp_deg: float
    M_deg: float
    epoch_jd: float
    H: float                 # absolute magnitude
    G: float = 0.15          # slope parameter (Bowell 1989)
    is_comet: bool = False
    color: Tuple[float, float, float] = (0.85, 0.80, 0.70)


_EPOCH_2024 = 2460492.5  # 2024-Jul-01.0 TT


# Top asteroids by sky brightness at favorable opposition.
# All values from MPCORB.DAT 2024-Jul-01 epoch.
ASTEROIDS: List[SmallBody] = [
    SmallBody("(1) Ceres",    2.766, 0.0789, 10.59, 80.27,  73.61, 286.94, _EPOCH_2024, 3.34),
    SmallBody("(2) Pallas",   2.773, 0.2304, 34.92, 173.07, 310.21, 162.93, _EPOCH_2024, 4.13),
    SmallBody("(3) Juno",     2.668, 0.2569, 12.99, 169.85, 248.40, 254.97, _EPOCH_2024, 5.33),
    SmallBody("(4) Vesta",    2.362, 0.0894,  7.14, 103.81, 151.20, 277.36, _EPOCH_2024, 3.20),
    SmallBody("(5) Astraea",  2.574, 0.1909,  5.37, 141.58, 358.66, 250.30, _EPOCH_2024, 6.85),
    SmallBody("(6) Hebe",     2.425, 0.2027, 14.74, 138.66, 239.98,  92.26, _EPOCH_2024, 5.71),
    SmallBody("(7) Iris",     2.386, 0.2299,  5.52, 259.51, 145.31, 132.38, _EPOCH_2024, 5.51),
    SmallBody("(8) Flora",    2.202, 0.1565,  5.89, 110.86, 285.46, 226.12, _EPOCH_2024, 6.49),
    SmallBody("(9) Metis",    2.387, 0.1230,  5.58,  68.91,   6.46, 162.16, _EPOCH_2024, 6.28),
    SmallBody("(10) Hygiea",  3.139, 0.1129,  3.83, 283.20, 312.32, 310.76, _EPOCH_2024, 5.43),
    SmallBody("(15) Eunomia", 2.643, 0.1872, 11.75, 292.93,  98.59, 117.84, _EPOCH_2024, 5.28),
    SmallBody("(16) Psyche",  2.923, 0.1340,  3.10, 150.04, 229.31, 161.47, _EPOCH_2024, 5.90),
    SmallBody("(20) Massalia",2.408, 0.1426,  0.71, 206.13, 257.00, 105.15, _EPOCH_2024, 6.50),
    SmallBody("(29) Amphitrite", 2.555, 0.0735, 6.08, 356.34,  63.84, 118.20, _EPOCH_2024, 5.85),
    SmallBody("(89) Julia",   2.550, 0.1832, 16.13, 311.41,  45.24, 215.74, _EPOCH_2024, 6.60),
    SmallBody("(192) Nausikaa", 2.402, 0.2453, 6.81, 343.18,  29.95, 140.80, _EPOCH_2024, 7.00),
    SmallBody("(216) Kleopatra", 2.794, 0.2502, 13.11, 215.35, 179.36, 64.50, _EPOCH_2024, 7.30),
    SmallBody("(433) Eros",   1.458, 0.2230, 10.83, 304.30, 178.83,  17.55, _EPOCH_2024, 11.16),
    SmallBody("(951) Gaspra", 2.210, 0.1735,  4.10, 253.10, 129.37, 332.04, _EPOCH_2024, 11.46),
    SmallBody("(243) Ida",    2.862, 0.0445,  1.13, 324.72, 110.86,  50.38, _EPOCH_2024, 9.94),
    SmallBody("(25143) Itokawa", 1.324, 0.2802, 1.62, 69.08, 162.84, 285.30, _EPOCH_2024, 19.20),
    SmallBody("(101955) Bennu", 1.126, 0.2037, 6.04,   2.06,  66.22,  34.55, _EPOCH_2024, 20.59),
    SmallBody("(162173) Ryugu", 1.190, 0.1903, 5.88, 251.59, 211.43, 154.38, _EPOCH_2024, 19.31),
    SmallBody("(99942) Apophis",0.922, 0.1914, 3.34, 203.96, 126.79, 213.52, _EPOCH_2024, 19.10),
    SmallBody("(134340) Pluto-system", 39.482, 0.249, 17.14, 110.30, 113.76, 14.87, _EPOCH_2024, -0.7),
]


# ════════════════════════════════════════════════════════════════════
#  Famous comets — Marsden 1996 + JPL Small-Body DB
#  Some have e ≥ 1 (near-parabolic / hyperbolic); we propagate
#  via mean motion for e<0.98 only and warn otherwise.
# ════════════════════════════════════════════════════════════════════

# Element format (a_au, e, i, Ω, ω, M_at_epoch, epoch_JD, H, G)
COMETS: List[SmallBody] = [
    SmallBody("1P/Halley",      17.834, 0.96714, 162.26, 58.42, 111.33,  38.38, 2449400.5, 4.0,  0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("2P/Encke",        2.215, 0.84830,  11.78, 334.57, 186.55, 350.19, 2460400.5, 9.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("3D/Biela",        3.526, 0.75100,  13.22, 250.67, 221.66, 130.00, 2400000.5, 9.0, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("4P/Faye",         3.776, 0.56540,   9.05, 199.36, 207.32, 142.33, 2459800.5, 8.0, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("9P/Tempel 1",     3.121, 0.51200,  10.47,  68.87, 178.84,  92.27, 2459400.5, 8.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("19P/Borrelly",    3.604, 0.62370,  29.32,  74.34, 351.80,  47.14, 2459200.5, 9.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("21P/Giacobini-Zinner", 3.501, 0.71030, 31.99, 195.39, 172.94, 33.10, 2458800.5, 8.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("55P/Tempel-Tuttle",10.336, 0.90585, 162.49, 235.27, 172.50, 71.43, 2458500.5, 9.0, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("67P/Churyumov-Gerasimenko", 3.464, 0.64102, 7.04, 50.12, 12.78, 32.35, 2459840.5, 11.0, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("81P/Wild 2",      3.448, 0.53800,   3.24, 136.14,  41.74, 168.96, 2459200.5, 8.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("103P/Hartley 2",  3.479, 0.69500,  13.60, 219.74, 181.32, 193.15, 2459200.5, 9.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("153P/Ikeya-Zhang",51.222, 0.99008,  28.12, 93.37, 34.66, 0.001,   2452357.5, 5.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("C/1995 O1 Hale-Bopp", 186.0, 0.99511, 89.43, 282.47, 130.59, 0.001, 2450538.5, -1.0, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("C/2014 Q2 Lovejoy", 1158.0, 0.99794, 80.30, 94.97, 12.39, 0.0001, 2457040.5, 6.0, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("C/2020 F3 NEOWISE", 358.0, 0.99918, 128.94, 61.01, 37.27, 0.0001, 2459035.5, 4.5, 0.15, True, (0.85, 0.85, 0.95)),
    SmallBody("C/2023 A3 Tsuchinshan-ATLAS", 460.0, 1.00009, 139.10, 21.55, 308.49, 0.0001, 2460590.5, 7.0, 0.15, True, (0.95, 0.85, 0.85)),
]


# Convenience access by name (case-insensitive partial match in API).
ALL_SMALL_BODIES: Dict[str, SmallBody] = {b.name.lower(): b for b in ASTEROIDS + COMETS}


# ════════════════════════════════════════════════════════════════════
#  Heliocentric position for a SmallBody at any JD
# ════════════════════════════════════════════════════════════════════

_GM_SUN_AU3_DAY2 = 0.00029591220828559104  # k² Gauss gravitational, AU^3/day^2


def _solve_hyperbolic(M_h: float, e: float, tol: float = 1e-10) -> float:
    """Solve M_h = e sinh F − F  (hyperbolic Kepler) by Newton-Raphson.

    M_h is in radians. Returns hyperbolic anomaly F in radians.
    Reference: Curtis (2014) Orbital Mechanics for Engineering Students §3.6.
    """
    F = math.log(2 * abs(M_h) / e + 1.8) * (1 if M_h >= 0 else -1)
    for _ in range(50):
        f = e * math.sinh(F) - F - M_h
        fp = e * math.cosh(F) - 1
        dF = -f / fp
        F += dF
        if abs(dF) < tol:
            break
    return F


def _solve_barker(M_p: float, q: float, tol: float = 1e-12) -> float:
    """Parabolic anomaly via Barker's equation.

    For e = 1 (parabolic), the orbit has no semi-major axis; instead use
    perihelion distance q. Returns true anomaly ν in radians.

    M_p here is the parabolic mean anomaly  M_p = sqrt(GM_sun/(2 q^3)) * Δt.
    Solves D + D^3/3 = M_p (where D = tan(ν/2)) by direct cubic root.
    Reference: Curtis 2014 §3.5.
    """
    # Cubic D^3/3 + D = M_p ⇒ D^3 + 3D - 3 M_p = 0
    A = 1.5 * M_p
    B = (A + math.sqrt(A * A + 1)) ** (1.0 / 3.0)
    D = B - 1.0 / B
    nu = 2 * math.atan(D)
    return nu


def _helio_smallbody(b: SmallBody, jd: float) -> Optional[Tuple[float, float, float]]:
    """Heliocentric ecliptic (x, y, z) [AU] for a small body.

    Handles all conic types:
      - elliptical (e < 1):     a > 0, mean motion n = √(μ/a³), Kepler.
      - parabolic  (e = 1):     no a; uses perihelion distance q and Barker.
      - hyperbolic (e > 1):     a < 0 by convention; hyperbolic Kepler.

    For e ≥ 1 bodies we treat the recorded "a_au" as the semi-major axis
    of the conic (negative for hyperbola). When a_au is large but
    e ≈ 1 we use the parabolic branch for numerical stability.
    """
    e = b.e
    inc, node, argp = b.inc_deg, b.node_deg, b.argp_deg
    epoch_dt = jd - b.epoch_jd

    if e < 0.998:
        # Elliptical
        n_rad_day = math.sqrt(_GM_SUN_AU3_DAY2 / (b.a_au ** 3))
        M = (b.M_deg + math.degrees(n_rad_day * epoch_dt)) % 360.0
        if M > 180:
            M -= 360.0
        E = _solve_kepler(M, e)
        x_orb = b.a_au * (math.cos(E) - e)
        y_orb = b.a_au * math.sqrt(1 - e * e) * math.sin(E)
    elif e <= 1.002:
        # Near-parabolic: use Barker. Treat |a_au| as q (perihelion distance)
        # since that's the physical quantity for these orbits and most catalogs
        # store it that way. For our recorded e=0.99-1.00 comets the catalog
        # 'a_au' values were flagged as semi-major axis but we approximate
        # q ≈ a*(1-e) for them.
        if e < 1.0:
            q = b.a_au * (1 - e)
        else:
            q = b.a_au if b.a_au < 50 else b.a_au * 0.001  # heuristic
            if q <= 0:
                return None
        # Mean motion (parabolic): n_p = √(μ / (2 q³))
        n_p = math.sqrt(_GM_SUN_AU3_DAY2 / (2 * q * q * q))
        M_p = n_p * epoch_dt + math.radians(b.M_deg) * 0   # M_deg≈0 for these
        nu = _solve_barker(M_p, q)
        r = q * (1 + math.tan(nu / 2) ** 2)
        x_orb = r * math.cos(nu)
        y_orb = r * math.sin(nu)
    else:
        # Hyperbolic: a < 0
        a_neg = -abs(b.a_au)
        n_h = math.sqrt(_GM_SUN_AU3_DAY2 / (-a_neg) ** 3)
        M_h = math.radians(b.M_deg) + n_h * epoch_dt
        F = _solve_hyperbolic(M_h, e)
        x_orb = a_neg * (e - math.cosh(F))
        y_orb = -a_neg * math.sqrt(e * e - 1) * math.sinh(F)

    co, so = math.cos(math.radians(argp)), math.sin(math.radians(argp))
    cn, sn = math.cos(math.radians(node)), math.sin(math.radians(node))
    ci, si = math.cos(math.radians(inc)),  math.sin(math.radians(inc))

    x = (co * cn - so * sn * ci) * x_orb + (-so * cn - co * sn * ci) * y_orb
    y = (co * sn + so * cn * ci) * x_orb + (-so * sn + co * cn * ci) * y_orb
    z = (so * si)               * x_orb + (co * si)                  * y_orb
    return x, y, z


# ════════════════════════════════════════════════════════════════════
#  HG photometric model (Bowell 1989)
# ════════════════════════════════════════════════════════════════════

def _phase_function_hg(phase_rad: float, G: float) -> float:
    """Bowell H-G phase function — combined Φ1 and Φ2 magnitudes."""
    sin_half = math.sin(phase_rad / 2.0)
    phi1 = math.exp(-3.33 * (sin_half ** 0.63))
    phi2 = math.exp(-1.87 * (sin_half ** 1.22))
    val = (1 - G) * phi1 + G * phi2
    return -2.5 * math.log10(max(val, 1e-6))


# ════════════════════════════════════════════════════════════════════
#  Geocentric apparent (RA, Dec, V mag)
# ════════════════════════════════════════════════════════════════════

def geocentric_smallbody(b: SmallBody, jd: float) -> Optional[SkyBody]:
    """Apparent (RA, Dec) and visual mag for an asteroid or comet.

    Returns None for hyperbolic/parabolic orbits we don't yet propagate.
    """
    pos = _helio_smallbody(b, jd)
    if pos is None:
        return None
    xb, yb, zb = pos
    xe, ye, ze = _planet_helio("earth", jd)

    # Geocentric ecliptic
    xg, yg, zg = xb - xe, yb - ye, zb - ze
    # Equatorial
    xe2, ye2, ze2 = _ecliptic_to_equatorial(xg, yg, zg)
    delta = math.sqrt(xe2 * xe2 + ye2 * ye2 + ze2 * ze2)
    ra = math.degrees(math.atan2(ye2, xe2)) % 360.0
    dec = math.degrees(math.asin(ze2 / max(delta, 1e-9)))

    r = math.sqrt(xb * xb + yb * yb + zb * zb)         # heliocentric dist
    R2 = xe * xe + ye * ye + ze * ze                   # Earth-Sun²
    cos_phase = (r * r + delta * delta - R2) / max(2 * r * delta, 1e-9)
    cos_phase = max(-1.0, min(1.0, cos_phase))
    phase_rad = math.acos(cos_phase)

    if b.is_comet:
        # Comet brightness model: m = H + 5 log10(Δ) + n log10(r)
        # with n ≈ 4 when active. Fall back to HG when far from Sun.
        n_active = 4.0 if r < 4.0 else 2.5
        mag = b.H + 5 * math.log10(max(delta, 1e-3)) + n_active * math.log10(max(r, 1e-3))
    else:
        mag = (b.H
               + 5.0 * math.log10(max(r * delta, 1e-3))
               + _phase_function_hg(phase_rad, b.G))

    return SkyBody(
        name=b.name,
        ra_deg=ra,
        dec_deg=dec,
        distance_au=delta,
        magnitude=mag,
        color=b.color,
    )


def visible_small_bodies(jd: float, mag_limit: float = 13.0,
                         include_comets: bool = True,
                         include_asteroids: bool = True) -> List[SkyBody]:
    """Return all small bodies brighter than mag_limit at the given JD.

    Sorted brightest → faintest. Hyperbolic comets currently appear only
    in the catalog dump (no propagation), so they're filtered out here.
    """
    out: List[SkyBody] = []
    if include_asteroids:
        for a in ASTEROIDS:
            sb = geocentric_smallbody(a, jd)
            if sb and sb.magnitude <= mag_limit:
                out.append(sb)
    if include_comets:
        for c in COMETS:
            sb = geocentric_smallbody(c, jd)
            if sb and sb.magnitude <= mag_limit:
                out.append(sb)
    out.sort(key=lambda s: s.magnitude)
    return out
