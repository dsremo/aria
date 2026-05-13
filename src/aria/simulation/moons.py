"""Major planetary satellites — geocentric apparent positions.

Covers the moons that are routinely targets of amateur observation or
historic interest. Position model: planet-centric Keplerian elements
(a, e, i, Ω, ω, M at epoch, period) added to the parent planet's
heliocentric position. Inclinations are taken with respect to the
ecliptic to keep the chain simple — for the Galilean moons the
~0.5° error vs. the Jovian-equatorial element set is below other
ephemeris noise in this codebase.

Element sources (all public-domain):
- JPL Horizons mean elements at J2000 (Jupiter satellites: Lieske 1998
  E5 reference set; Saturn satellites: Vienne & Duriez 1992)
- Lainey et al. (2009) for the Martian moons
- USNO/NASA fact sheets for radii and absolute magnitudes

For sub-arcsecond observation prediction (occultations, mutual events)
use Lieske's E2x3 / Lainey's TASS1.6 or query JPL HORIZONS through
SPICE. This module is for sky-rendering and education, not navigation.

References:
    Lieske, J. H. (1998) "Galilean satellite ephemerides E5." A&A 129:205
    Vienne, A. & Duriez, L. (1992) A&A 257:331
    Lainey, V. et al. (2009) Icarus 199:120
    NASA NSSDCA planetary fact sheets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from aria.simulation.solar_system import (
    EPSILON_J2000_DEG,
    SkyBody,
    _ecliptic_to_equatorial,
    _solve_kepler,
    heliocentric_ecliptic,
)


_AU_KM = 149597870.7


@dataclass
class Moon:
    """A natural satellite with planet-relative Keplerian elements."""
    name: str
    parent: str               # 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto'
    a_km: float               # semi-major axis around parent [km]
    e: float
    inc_deg: float            # inclination wrt ecliptic
    node_deg: float           # long. asc. node wrt ecliptic
    argp_deg: float           # arg of pericenter
    M_deg: float              # mean anomaly at epoch
    period_d: float           # orbital period [days]
    epoch_jd: float
    radius_km: float
    H_mag: float              # absolute V mag at 1 AU, 0° phase
    color: Tuple[float, float, float] = (0.85, 0.82, 0.75)


# ════════════════════════════════════════════════════════════════════
#  Major moons — element values from JPL HORIZONS J2000 mean orbit
#  (Jovian-equatorial elements rotated to ecliptic where needed).
# ════════════════════════════════════════════════════════════════════

# Martian moons (Lainey 2009)
MARS_MOONS: List[Moon] = [
    Moon("Phobos", "mars", 9376, 0.0151, 26.04, 49.57, 150.057, 91.60, 0.31891, 2451545.0, 11.27, 11.8),
    Moon("Deimos", "mars", 23463, 0.0002, 27.58, 79.40, 290.496, 320.40, 1.26244, 2451545.0, 6.27, 12.4),
]

# Jovian Galilean moons (Lieske 1998 E5)
JUPITER_MOONS: List[Moon] = [
    Moon("Io",       "jupiter", 421800,  0.0041, 0.040, 43.977, 84.129,  342.021, 1.769138, 2451545.0, 1821.6, -1.68, (0.95, 0.85, 0.45)),
    Moon("Europa",   "jupiter", 671100,  0.0094, 0.470, 219.106, 88.970,  171.016, 3.551181, 2451545.0, 1560.8, -1.41, (0.85, 0.82, 0.75)),
    Moon("Ganymede", "jupiter", 1070400, 0.0013, 0.195, 63.552, 192.417, 317.540, 7.154553, 2451545.0, 2634.1, -2.09, (0.78, 0.74, 0.66)),
    Moon("Callisto", "jupiter", 1882700, 0.0074, 0.281, 298.848, 52.643,  181.408, 16.689018, 2451545.0, 2410.3, -1.05, (0.55, 0.50, 0.42)),
]

# Saturnian moons (Vienne & Duriez 1992) — major + Iapetus
SATURN_MOONS: List[Moon] = [
    Moon("Mimas",    "saturn", 185539,  0.0196, 1.574, 173.027, 14.352,  255.312, 0.942422, 2451545.0, 198.2, 3.3),
    Moon("Enceladus","saturn", 238040,  0.0047, 0.009, 169.506, 211.923, 197.047, 1.370218, 2451545.0, 252.1, 2.1),
    Moon("Tethys",   "saturn", 294670,  0.0001, 1.091, 167.624, 262.845,  189.003, 1.887802, 2451545.0, 533.0, 0.6),
    Moon("Dione",    "saturn", 377420,  0.0022, 0.028, 169.328, 168.821, 65.000,  2.736915, 2451545.0, 561.7, 0.8),
    Moon("Rhea",     "saturn", 527070,  0.0010, 0.331, 311.531, 256.609, 311.551, 4.518212, 2451545.0, 763.8, 0.1),
    Moon("Titan",    "saturn", 1221870, 0.0288, 0.280,  28.060, 180.532, 163.310, 15.945421, 2451545.0, 2574.7, -1.28, (0.95, 0.78, 0.45)),
    Moon("Iapetus",  "saturn", 3560820, 0.0286, 7.570, 81.105, 271.606,  201.789, 79.330183, 2451545.0, 734.5, 1.6),
]

# Uranian — Titania & Oberon (brightest, naked-eye in 8" telescope)
URANUS_MOONS: List[Moon] = [
    Moon("Titania", "uranus", 435910, 0.0011, 97.929, 167.612, 165.281, 297.987, 8.706235, 2451545.0, 788.9, 1.0),
    Moon("Oberon",  "uranus", 583520, 0.0014, 97.852, 167.770,  90.020,  41.481, 13.463239, 2451545.0, 761.4, 1.5),
    Moon("Ariel",   "uranus", 191020, 0.0012, 97.696, 167.754, 115.349, 156.135, 2.520379, 2451545.0, 578.9, 1.45),
    Moon("Umbriel", "uranus", 266300, 0.0039, 97.692, 167.755,  84.709,  108.05, 4.144177, 2451545.0, 584.7, 2.10),
]

# Neptunian — Triton (only major moon)
NEPTUNE_MOONS: List[Moon] = [
    Moon("Triton", "neptune", 354760, 0.0000, 156.834, 130.880, 344.046, 264.775, 5.876854, 2451545.0, 1353.4, -1.20),
]

# Plutonian — Charon (binary system effectively)
PLUTO_MOONS: List[Moon] = [
    Moon("Charon", "pluto", 19591, 0.0002, 112.783, 223.046,  64.531, 132.038, 6.387230, 2451545.0, 606.0, 1.0),
]


ALL_MOONS: List[Moon] = (
    MARS_MOONS + JUPITER_MOONS + SATURN_MOONS
    + URANUS_MOONS + NEPTUNE_MOONS + PLUTO_MOONS
)


# ════════════════════════════════════════════════════════════════════
#  Position computation
# ════════════════════════════════════════════════════════════════════

def planetcentric_position(m: Moon, jd: float) -> Tuple[float, float, float]:
    """Position of a moon relative to its parent planet in AU (ecliptic).

    Mean motion driven by orbital period (which already encodes GM_planet),
    so we don't need μ_planet here.
    """
    n_rev_day = 1.0 / m.period_d
    M = (m.M_deg + 360.0 * n_rev_day * (jd - m.epoch_jd)) % 360.0
    if M > 180:
        M -= 360.0
    E = _solve_kepler(M, m.e)
    cosE, sinE = math.cos(E), math.sin(E)
    x_orb = m.a_km * (cosE - m.e)
    y_orb = m.a_km * math.sqrt(1 - m.e * m.e) * sinE

    co, so = math.cos(math.radians(m.argp_deg)), math.sin(math.radians(m.argp_deg))
    cn, sn = math.cos(math.radians(m.node_deg)), math.sin(math.radians(m.node_deg))
    ci, si = math.cos(math.radians(m.inc_deg)),  math.sin(math.radians(m.inc_deg))

    x = (co * cn - so * sn * ci) * x_orb + (-so * cn - co * sn * ci) * y_orb
    y = (co * sn + so * cn * ci) * x_orb + (-so * sn + co * cn * ci) * y_orb
    z = (so * si)               * x_orb + (co * si)                  * y_orb
    # km → AU
    return x / _AU_KM, y / _AU_KM, z / _AU_KM


def heliocentric_moon(m: Moon, jd: float) -> Tuple[float, float, float]:
    """Moon's position relative to the Sun, in AU (ecliptic)."""
    px, py, pz = heliocentric_ecliptic(m.parent, jd)
    mx, my, mz = planetcentric_position(m, jd)
    return px + mx, py + my, pz + mz


def geocentric_moon(m: Moon, jd: float) -> SkyBody:
    """Apparent geocentric (RA, Dec) and visible magnitude for a moon."""
    xb, yb, zb = heliocentric_moon(m, jd)
    xe, ye, ze = heliocentric_ecliptic("earth", jd)
    xg, yg, zg = xb - xe, yb - ye, zb - ze
    xe2, ye2, ze2 = _ecliptic_to_equatorial(xg, yg, zg)
    delta = math.sqrt(xe2 * xe2 + ye2 * ye2 + ze2 * ze2)
    ra = math.degrees(math.atan2(ye2, xe2)) % 360.0
    dec = math.degrees(math.asin(ze2 / max(delta, 1e-9)))

    # Magnitude: V = H + 5 log10(r * Δ); ignore phase function (small for moons).
    r = math.sqrt(xb * xb + yb * yb + zb * zb)
    mag = m.H_mag + 5 * math.log10(max(r * delta, 1e-3))

    return SkyBody(
        name=m.name,
        ra_deg=ra,
        dec_deg=dec,
        distance_au=delta,
        magnitude=mag,
        color=m.color,
    )


def visible_moons(jd: float, mag_limit: float = 14.0) -> List[SkyBody]:
    """Return all moons brighter than mag_limit at the given JD, sorted bright→faint."""
    out: List[SkyBody] = []
    for m in ALL_MOONS:
        sb = geocentric_moon(m, jd)
        if sb.magnitude <= mag_limit:
            out.append(sb)
    out.sort(key=lambda s: s.magnitude)
    return out
