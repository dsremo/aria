"""Star field visualization data — what the crew sees out the window.

For an interstellar spacecraft, the view changes dramatically:
- At 0.01c, aberration shifts stars forward by ~0.6°
- At 0.1c, aberration compresses the forward hemisphere significantly
- At 0.5c, nearly all stars appear in the forward 60° cone
- Doppler shift: forward stars blue-shift, aft stars red-shift

This module provides:
1. Bright star catalog (Hipparcos naked-eye, ~5000 stars to mag 6)
2. Position computation with proper motion at arbitrary epoch
3. B-V color index to RGB conversion
4. Relativistic aberration and Doppler shift for moving spacecraft
5. Constellation line data (Western IAU)

Data format studied from Stellarium stars/hip_gaia3 (GPL, data is
public domain — Hipparcos/Gaia catalogs are ESA open data).
Algorithms from Stellarium Star.hpp position propagation.

References:
    ESA (1997). "The Hipparcos and Tycho Catalogues." ESA SP-1200.
    Penrose, R. (1959). "The apparent shape of a relativistically moving
    sphere." Proc. Cambridge Phil. Soc. 55, 137-139.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


# HYG-Database v3 (Hipparcos + Yale + Gliese), David Nash, public domain.
# Filtered to V≤9 (~84k stars; binocular limit). Replaces older BSC5 catalog.
_HYG_PATH = Path(__file__).resolve().parent / "_data" / "hyg.json"
_HYG_CACHE: Optional[List["Star"]] = None


@dataclass
class Star:
    """A star from the catalog."""
    hip_id: int           # Hipparcos catalog ID
    ra_deg: float         # Right ascension J2000 [deg]
    dec_deg: float        # Declination J2000 [deg]
    vmag: float           # Visual magnitude
    bv_color: float       # B-V color index
    pm_ra_mas_yr: float   # Proper motion in RA [mas/yr]
    pm_dec_mas_yr: float  # Proper motion in Dec [mas/yr]
    parallax_mas: float   # Parallax [mas]
    name: str = ""        # Common name (e.g., "Sirius")


# ══════════════════════════════════════════════════════════════════
#  Built-in bright star catalog (top 50 brightest + navigation stars)
# ══════════════════════════════════════════════════════════════════

# Source: Hipparcos catalog (ESA SP-1200), J2000.0 epoch
# These are public domain astronomical data, not copyrightable
BRIGHT_STARS: List[Star] = [
    Star(32349, 101.287, -16.716, -1.46, 0.00, -546.01, -1223.07, 379.21, "Sirius"),
    Star(30438, 95.988, -52.696, -0.72, 0.15, -3.99, -0.61, 10.43, "Canopus"),
    Star(69673, 213.915, 19.182, -0.05, 1.23, -1093.45, -1999.40, 88.85, "Arcturus"),
    Star(71683, 219.902, -60.834, -0.01, 0.71, -3678.19, 481.84, 742.12, "Alpha Centauri A"),
    Star(91262, 279.235, 38.784, 0.03, 0.00, 200.94, 286.23, 128.93, "Vega"),
    Star(24436, 78.634, -8.202, 0.12, 0.13, 1.87, -0.56, 3.54, "Rigel"),
    Star(37279, 114.827, 5.225, 0.34, 0.42, -714.59, -1036.80, 284.56, "Procyon"),
    Star(24608, 79.172, 45.998, 0.45, 0.80, 87.65, -427.13, 77.29, "Capella"),
    Star(27989, 88.793, 7.407, 0.50, 1.85, 27.33, 26.27, 4.22, "Betelgeuse"),
    Star(7588, 24.429, -57.237, 0.46, 0.22, 87.00, -40.08, 23.39, "Achernar"),
    Star(68702, 210.956, -60.373, 0.61, -0.23, -33.96, -23.16, 8.32, "Beta Centauri"),
    Star(97649, 297.696, 8.868, 0.77, 0.22, 536.23, 385.54, 194.95, "Altair"),
    Star(60718, 186.650, -63.099, 0.77, -0.24, -42.50, -31.73, 10.13, "Alpha Crucis"),
    Star(21421, 68.980, 16.509, 0.85, 1.54, 62.78, -189.36, 48.94, "Aldebaran"),
    Star(65474, 201.298, -11.161, 0.97, -0.23, -42.35, -30.67, 12.44, "Spica"),
    Star(80763, 247.352, -26.432, 0.96, 1.83, -12.11, -23.30, 5.40, "Antares"),
    Star(37826, 116.329, 28.026, 1.14, 1.00, -625.69, -45.95, 96.74, "Pollux"),
    Star(113368, 344.413, -29.622, 1.16, -0.03, 329.22, -164.22, 130.08, "Fomalhaut"),
    Star(49669, 152.093, 11.967, 1.35, -0.11, -249.40, 4.91, 42.09, "Regulus"),
    Star(62434, 191.930, -59.689, 1.33, -0.22, -35.37, -14.86, 8.68, "Beta Crucis"),
    # Navigation stars for celestial navigation
    Star(11767, 37.955, 89.264, 2.02, 0.60, 44.22, -11.74, 7.54, "Polaris"),
    Star(54061, 166.113, 61.751, 1.77, 0.08, -136.46, -35.25, 26.38, "Dubhe"),
    Star(67301, 206.885, 49.313, 1.86, -0.02, -121.23, -15.56, 32.39, "Alkaid"),
    Star(746, 2.097, 29.091, 2.06, -0.11, 135.68, -162.95, 33.60, "Alpheratz"),
    Star(9884, 31.793, 23.462, 2.00, 0.48, 175.90, -148.19, 50.09, "Hamal"),
    # Nearby stars (important for interstellar navigation at 0.1c)
    Star(70890, 217.449, -62.682, 11.13, 1.81, -3775.64, 765.54, 768.53, "Proxima Centauri"),
    Star(71681, 219.896, -60.838, 1.35, 0.90, -3600.35, 952.11, 742.12, "Alpha Centauri B"),
    Star(54035, 165.834, 35.970, 7.47, 1.57, -580.24, -4765.96, 392.56, "Lalande 21185"),
    Star(87937, 269.452, 4.668, 9.54, 1.74, -798.71, 10337.77, 548.31, "Barnard's Star"),
    Star(108870, 330.895, -56.788, 4.68, 1.09, 3961.92, -2538.36, 276.07, "Epsilon Indi"),
    Star(104214, 316.726, 38.762, 5.21, 1.07, 4155.10, 3259.78, 287.18, "61 Cygni A"),
    Star(16537, 53.232, -9.458, 3.72, 0.88, -976.43, 17.97, 310.94, "Epsilon Eridani"),
    Star(8102, 26.017, -15.937, 3.49, 0.73, -1721.05, 854.16, 273.96, "Tau Ceti"),
    Star(36208, 111.848, 30.256, 6.73, 1.44, 169.90, -97.78, 106.56, "Pollux-B"),
    # Pleiades (open cluster, navigation reference)
    Star(17702, 56.871, 24.105, 2.86, -0.08, 20.10, -45.39, 8.87, "Alcyone"),
    Star(17608, 56.581, 24.467, 4.30, -0.09, 19.71, -44.18, 8.64, "Atlas"),
    Star(17847, 57.291, 24.054, 3.62, -0.07, 19.35, -43.67, 8.09, "Maia"),
    # More bright stars
    Star(25428, 81.573, 6.350, 1.64, -0.03, 5.49, -16.13, 7.20, "Bellatrix"),
    Star(26311, 82.061, -0.299, 1.69, -0.19, 0.64, -1.06, 1.65, "Alnilam"),
    Star(26727, 84.053, -1.202, 1.74, -0.22, 1.49, -0.68, 4.21, "Alnitak"),
    Star(25336, 83.001, -0.299, 2.23, -0.21, 2.43, -0.56, 1.25, "Mintaka"),
    Star(45238, 138.300, -69.717, 1.67, -0.14, -29.34, 19.31, 10.43, "Miaplacidus"),
    Star(39429, 120.896, -40.003, 1.50, 1.00, -23.21, 13.40, 5.84, "Suhail"),
    Star(33579, 104.656, -28.972, 2.04, -0.07, -6.08, -3.36, 2.26, "Naos"),
    Star(50583, 154.993, 19.842, 2.14, 0.13, -249.40, 4.91, 40.23, "Algieba"),
    Star(72622, 222.677, 74.156, 4.41, 1.51, -1.10, 0.20, 8.27, "Edasich"),
    # Asterisms
    Star(3179, 10.127, 56.537, 2.23, 0.30, 523.39, -179.45, 59.89, "Schedar"),
    Star(4427, 14.177, 60.717, 2.28, 0.38, 50.36, -32.17, 32.81, "Caph"),
    Star(5447, 17.435, 35.621, 2.07, -0.15, 95.52, -111.17, 24.36, "Mirach"),
    Star(14135, 45.570, 4.089, 2.54, 1.65, -11.53, -78.76, 13.27, "Menkar"),
    Star(15863, 51.081, 49.861, 1.79, 0.48, 23.75, -26.23, 5.74, "Mirfak"),
    Star(18543, 59.463, 40.010, 2.85, 1.13, -175.11, -112.23, 34.07, "Atik"),
    Star(20889, 67.154, 19.180, 3.53, 0.99, 107.17, -36.77, 21.17, "Ain"),
    Star(21421, 68.980, 16.509, 0.85, 1.54, 62.78, -189.36, 48.94, "Aldebaran"),
    # Southern Cross neighbors
    Star(59747, 183.786, -58.749, 2.79, 1.60, -24.50, -4.82, 7.15, "Delta Crucis"),
    Star(61084, 187.791, -57.113, 1.63, 1.59, -14.68, -11.82, 8.25, "Gacrux"),
    Star(66657, 204.972, -53.466, 2.17, -0.18, -44.95, -6.25, 8.54, "Muhlifain"),
    Star(67472, 207.371, -41.688, 2.06, -0.11, -27.99, -1.47, 6.17, "Alpha Muscae"),
    # Scorpius
    Star(78820, 241.359, -19.806, 2.89, -0.07, -10.21, -23.23, 6.52, "Dschubba"),
    Star(82396, 252.541, -34.293, 2.41, -0.20, -1.12, -23.35, 7.12, "Sargas"),
    Star(82514, 252.969, -26.434, 2.82, -0.04, -0.31, -4.22, 5.52, "Larawag"),
    Star(83081, 254.660, -34.293, 2.99, -0.15, 2.15, -17.03, 4.10, "Girtab"),
    Star(84143, 258.038, -43.239, 1.86, 0.39, -9.03, -22.53, 5.74, "Shaula"),
    # Cygnus
    Star(102098, 310.358, 45.280, 1.25, 0.09, 2.01, 1.85, 2.31, "Deneb"),
    Star(95947, 292.680, 27.960, 2.23, 1.02, 43.89, 48.92, 20.31, "Albireo"),
    Star(97278, 296.565, 45.131, 2.46, 0.40, 128.31, -225.11, 28.27, "Sadr"),
    # Miscellaneous navigation
    Star(82273, 251.493, 14.390, 2.76, 1.17, 114.27, 227.74, 42.05, "Kornephoros"),
    Star(86032, 263.403, 12.560, 2.08, 0.16, -8.11, 33.96, 10.56, "Rasalhague"),
    Star(92420, 282.520, 33.363, 2.99, 0.08, -7.54, 14.17, 9.33, "Sulafat"),
    Star(100345, 304.513, 14.595, 3.53, -0.01, 92.49, 38.37, 22.85, "Rotanev"),
]


# ══════════════════════════════════════════════════════════════════
#  Yale Bright Star Catalog (BSC5) — 9096 stars to V≈6.5
# ══════════════════════════════════════════════════════════════════


def load_hyg(path: Optional[Path] = None) -> List[Star]:
    """Load the HYG-Database v3 (Hipparcos+Yale+Gliese) star catalog.

    ~84,000 stars to V≤9 (binocular limit), parsed from the public-domain
    catalog by David Nash. Reads on first call, caches in memory.

    Returns the curated BRIGHT_STARS list as a fallback in stripped-down
    deployments where the data file is absent.

    Source format is produced by scripts/parse_hyg.py.
    """
    global _HYG_CACHE
    if _HYG_CACHE is not None:
        return _HYG_CACHE

    p = Path(path) if path else _HYG_PATH
    if not p.exists() or p.stat().st_size < 1024:
        _HYG_CACHE = list(BRIGHT_STARS)
        return _HYG_CACHE

    with p.open() as fh:
        records = json.load(fh)

    stars: List[Star] = []
    for r in records:
        if r.get("name") == "Sol":
            # The Sun has no meaningful sky-position; skip in star catalog
            # (it's rendered as a planet by solar_system.py).
            continue
        # Prefer Hipparcos ID for hip_id (so constellation lines that key
        # off HIP keep working). HYG entries that aren't in Hipparcos fall
        # back to the HYG internal id encoded as a negative number to keep
        # IDs unique across namespaces.
        hip = r.get("hip", 0)
        hip_id = hip if hip > 0 else -int(r["id"])
        stars.append(Star(
            hip_id=hip_id,
            ra_deg=r["ra"],
            dec_deg=r["dec"],
            vmag=r["mag"],
            bv_color=r["bv"],
            pm_ra_mas_yr=r["pmra"],
            pm_dec_mas_yr=r["pmdec"],
            parallax_mas=0.0,   # not stored in compact format
            name=r.get("name", ""),
        ))
    _HYG_CACHE = stars
    return stars


# Backwards-compatibility alias for callers still importing load_bsc5.
load_bsc5 = load_hyg


# ══════════════════════════════════════════════════════════════════
#  Constellation lines (Western IAU, HIP ID pairs)
# ══════════════════════════════════════════════════════════════════

CONSTELLATION_LINES: Dict[str, List[Tuple[int, int]]] = {
    "Orion": [(27989, 26727), (26727, 25336), (25336, 25930), (25930, 26311),
              (26311, 27989), (25336, 24436), (26727, 28614), (25930, 25281)],
    "Ursa Major": [(54061, 53910), (53910, 58001), (58001, 59774), (59774, 62956),
                   (62956, 65378), (65378, 67301)],
    "Crux": [(60718, 62434), (59747, 61084)],
    "Scorpius": [(80763, 78820), (78820, 78265), (78265, 77070), (80763, 81266),
                 (81266, 82396), (82396, 82514), (82514, 83081), (83081, 84143),
                 (84143, 86228), (86228, 87073)],
    "Centaurus": [(71683, 68702), (68702, 67472), (67472, 66657), (66657, 61932)],
}


# ══════════════════════════════════════════════════════════════════
#  B-V color index to RGB
# ══════════════════════════════════════════════════════════════════

def bv_to_rgb(bv: float) -> Tuple[float, float, float]:
    """Convert B-V color index to RGB (0-1 range).

    Uses the Ballesteros (2012) formula for blackbody color temperature
    mapping. Cel. Mech. Dyn. Astron. 113, 347-356.
    """
    # Clamp to valid range
    bv = max(-0.4, min(2.0, bv))

    # Color temperature from B-V (Ballesteros 2012)
    T = 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))

    # Planckian locus to RGB (simplified)
    if T < 3500:
        r, g, b = 1.0, 0.6, 0.3
    elif T < 5000:
        f = (T - 3500) / 1500
        r, g, b = 1.0, 0.6 + 0.3 * f, 0.3 + 0.4 * f
    elif T < 7000:
        f = (T - 5000) / 2000
        r, g, b = 1.0 - 0.1 * f, 0.9 + 0.1 * f, 0.7 + 0.3 * f
    elif T < 10000:
        f = (T - 7000) / 3000
        r, g, b = 0.9 - 0.2 * f, 1.0 - 0.1 * f, 1.0
    else:
        r, g, b = 0.7, 0.9, 1.0  # hot blue

    return (r, g, b)


# ══════════════════════════════════════════════════════════════════
#  Position computation with proper motion
# ══════════════════════════════════════════════════════════════════

def star_position_at_epoch(
    star: Star, years_from_j2000: float
) -> Tuple[float, float]:
    """Compute star position at arbitrary epoch using proper motion.

    Args:
        star: Star object
        years_from_j2000: years since J2000.0 (e.g., 226 for year 2226)

    Returns:
        (ra_deg, dec_deg) at the requested epoch
    """
    # Convert proper motion from mas/yr to deg/yr
    pm_ra_deg_yr = star.pm_ra_mas_yr / 3.6e6
    pm_dec_deg_yr = star.pm_dec_mas_yr / 3.6e6

    ra = star.ra_deg + pm_ra_deg_yr * years_from_j2000
    dec = star.dec_deg + pm_dec_deg_yr * years_from_j2000

    # Wrap RA to [0, 360)
    ra = ra % 360.0
    # Clamp Dec to [-90, 90]
    dec = max(-90.0, min(90.0, dec))

    return ra, dec


# ══════════════════════════════════════════════════════════════════
#  Relativistic aberration for moving spacecraft
# ══════════════════════════════════════════════════════════════════

def relativistic_aberration(
    ra_deg: float,
    dec_deg: float,
    velocity_direction: np.ndarray,
    beta: float,
) -> Tuple[float, float]:
    """Apply relativistic stellar aberration for a spacecraft at velocity beta*c.

    Stars shift toward the direction of motion. At 0.1c, the shift is
    ~5.7° for stars perpendicular to motion. At 0.5c, nearly all stars
    compress into the forward hemisphere.

    Args:
        ra_deg, dec_deg: star position [degrees]
        velocity_direction: (3,) unit vector of spacecraft motion (J2000)
        beta: v/c (spacecraft speed as fraction of light speed)

    Returns:
        (ra_aberrated, dec_aberrated) in degrees

    Reference: Penrose 1959 Proc. Cambridge Phil. Soc. 55 137.
    """
    if beta < 1e-10:
        return ra_deg, dec_deg

    gamma = 1.0 / math.sqrt(1.0 - beta ** 2)

    # Convert star direction to unit vector
    ra_rad = math.radians(ra_deg)
    dec_rad = math.radians(dec_deg)
    star_dir = np.array([
        math.cos(dec_rad) * math.cos(ra_rad),
        math.cos(dec_rad) * math.sin(ra_rad),
        math.sin(dec_rad),
    ])

    # Angle between star and velocity direction
    cos_theta = np.dot(star_dir, velocity_direction)
    cos_theta = max(-1.0, min(1.0, cos_theta))

    # Aberrated angle (relativistic formula)
    cos_theta_prime = (cos_theta + beta) / (1.0 + beta * cos_theta)

    # If the change is negligible, return original
    delta_cos = cos_theta_prime - cos_theta
    if abs(delta_cos) < 1e-15:
        return ra_deg, dec_deg

    # Reconstruct the aberrated direction
    # The aberration is along the velocity-star plane
    perp = star_dir - cos_theta * velocity_direction
    perp_norm = np.linalg.norm(perp)
    if perp_norm < 1e-15:
        # Star is along velocity direction
        return ra_deg, dec_deg

    perp_hat = perp / perp_norm
    sin_theta_prime = math.sqrt(max(0.0, 1.0 - cos_theta_prime ** 2))

    aberrated_dir = cos_theta_prime * velocity_direction + sin_theta_prime * perp_hat

    # Convert back to RA/Dec
    dec_new = math.degrees(math.asin(max(-1.0, min(1.0, aberrated_dir[2]))))
    ra_new = math.degrees(math.atan2(aberrated_dir[1], aberrated_dir[0])) % 360.0

    return ra_new, dec_new


def doppler_shift_color(bv: float, beta: float, cos_angle: float) -> float:
    """Compute Doppler-shifted B-V color index.

    Forward stars blue-shift (lower B-V), aft stars red-shift (higher B-V).

    Args:
        bv: original B-V color index
        beta: v/c
        cos_angle: cosine of angle between star direction and velocity

    Returns:
        Shifted B-V color index
    """
    if beta < 1e-10:
        return bv

    # Doppler factor
    doppler = math.sqrt((1.0 - beta) / (1.0 + beta)) if cos_angle > 0 else \
              math.sqrt((1.0 + beta) / (1.0 - beta))

    # Approximate B-V shift: bluer = lower B-V
    # Each factor of 2 in frequency shifts B-V by ~0.5
    shift = -0.5 * math.log2(max(doppler, 0.01)) * abs(cos_angle)
    return bv + shift


# ══════════════════════════════════════════════════════════════════
#  Generate star field data for Three.js visualization
# ══════════════════════════════════════════════════════════════════

def generate_star_field_data(
    years_from_j2000: float = 0.0,
    beta: float = 0.0,
    velocity_direction: Optional[np.ndarray] = None,
    catalog: Optional[List[Star]] = None,
    mag_limit: float = 6.5,
) -> List[Dict]:
    """Generate star field data for the web dashboard.

    Returns a list of dicts suitable for JSON serialization and
    Three.js BufferGeometry rendering.

    Args:
        years_from_j2000: epoch offset for proper motion
        beta: spacecraft velocity as fraction of c
        velocity_direction: (3,) unit vector of motion (for aberration)
        catalog: optional override; defaults to the full BSC5 (9096 stars)
        mag_limit: visual-magnitude cutoff (6.5 ≈ naked-eye limit)

    Returns:
        List of {ra, dec, mag, r, g, b, name, hip_id}
    """
    if catalog is None:
        catalog = load_hyg()
    stars = [s for s in catalog if s.vmag <= mag_limit]
    if velocity_direction is None:
        velocity_direction = np.array([1.0, 0.0, 0.0])
    velocity_direction = velocity_direction / max(np.linalg.norm(velocity_direction), 1e-15)

    result = []
    for star in stars:
        ra, dec = star_position_at_epoch(star, years_from_j2000)

        if beta > 1e-6:
            ra, dec = relativistic_aberration(ra, dec, velocity_direction, beta)
            cos_angle = np.dot(
                np.array([math.cos(math.radians(dec)) * math.cos(math.radians(ra)),
                          math.cos(math.radians(dec)) * math.sin(math.radians(ra)),
                          math.sin(math.radians(dec))]),
                velocity_direction,
            )
            bv = doppler_shift_color(star.bv_color, beta, cos_angle)
        else:
            bv = star.bv_color

        r, g, b = bv_to_rgb(bv)

        result.append({
            "ra": round(ra, 6),
            "dec": round(dec, 6),
            "mag": star.vmag,
            "r": round(r, 3),
            "g": round(g, 3),
            "b": round(b, 3),
            "name": star.name,
            "hip_id": star.hip_id,
        })

    return result
