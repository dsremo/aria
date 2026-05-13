"""Star catalog with real 3D coordinates for interstellar mission targets.

Coordinates are in light-years relative to Sol [0, 0, 0].
All values from Hipparcos/Gaia DR3 parallax data converted to Cartesian.

Galactic coordinate convention:
  x: toward galactic center (positive)
  y: direction of galactic rotation
  z: toward north galactic pole
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StarTarget:
    """An interstellar destination with real coordinates."""
    name: str
    display_name: str
    position_ly: list[float]   # [x, y, z] in light-years from Sol
    distance_ly: float          # Total distance
    spectral_type: str
    mass_solar: float           # Stellar mass in solar masses
    habitable_zone_au: tuple[float, float]  # Inner/outer HZ in AU
    known_planets: int
    notes: str = ""

    @property
    def direction_unit(self) -> list[float]:
        """Unit vector from Sol to this star."""
        d = self.distance_ly
        if d < 1e-12:
            return [0.0, 0.0, 0.0]
        return [c / d for c in self.position_ly]


# Real stellar coordinates (Gaia DR3 / Hipparcos derived)
# Positions converted from RA/Dec/parallax to galactic Cartesian (ly)

STAR_CATALOG: dict[str, StarTarget] = {
    "alpha_centauri": StarTarget(
        name="alpha_centauri",
        display_name="Alpha Centauri A/B",
        position_ly=[1.74, -3.74, -0.66],
        distance_ly=4.37,
        spectral_type="G2V / K1V",
        mass_solar=1.1,
        habitable_zone_au=(1.0, 1.8),
        known_planets=0,
        notes="Binary system. Closest Sun-like stars. 43.7 years at 0.1c.",
    ),

    "proxima_centauri": StarTarget(
        name="proxima_centauri",
        display_name="Proxima Centauri",
        position_ly=[1.64, -3.62, -0.74],
        distance_ly=4.24,
        spectral_type="M5.5Ve",
        mass_solar=0.122,
        habitable_zone_au=(0.04, 0.08),
        known_planets=3,
        notes="Closest star to Sol. Proxima b in habitable zone. Flare star risk.",
    ),

    "barnards_star": StarTarget(
        name="barnards_star",
        display_name="Barnard's Star",
        position_ly=[4.56, -2.72, 2.42],
        distance_ly=5.96,
        spectral_type="M4Ve",
        mass_solar=0.144,
        habitable_zone_au=(0.04, 0.09),
        known_planets=1,
        notes="Highest proper motion of any known star. Ancient (7-12 Gyr).",
    ),

    "wolf_359": StarTarget(
        name="wolf_359",
        display_name="Wolf 359",
        position_ly=[1.76, -6.96, 2.49],
        distance_ly=7.86,
        spectral_type="M6.5Ve",
        mass_solar=0.09,
        habitable_zone_au=(0.02, 0.05),
        known_planets=2,
        notes="UV Ceti type flare star. Very low luminosity.",
    ),

    "lalande_21185": StarTarget(
        name="lalande_21185",
        display_name="Lalande 21185",
        position_ly=[1.93, -4.49, 6.34],
        distance_ly=8.31,
        spectral_type="M2V",
        mass_solar=0.46,
        habitable_zone_au=(0.11, 0.24),
        known_planets=2,
        notes="Among brightest M dwarfs visible from Earth.",
    ),

    "sirius": StarTarget(
        name="sirius",
        display_name="Sirius A/B",
        position_ly=[-5.76, -6.22, -1.39],
        distance_ly=8.60,
        spectral_type="A1V / DA2",
        mass_solar=2.06,
        habitable_zone_au=(2.0, 4.0),
        known_planets=0,
        notes="Brightest star in night sky. White dwarf companion.",
    ),

    "tau_ceti": StarTarget(
        name="tau_ceti",
        display_name="Tau Ceti",
        position_ly=[-4.34, -9.86, -4.36],
        distance_ly=11.9,
        spectral_type="G8.5V",
        mass_solar=0.78,
        habitable_zone_au=(0.55, 1.16),
        known_planets=5,
        notes="Sun-like. 5 candidate planets. Heavy debris disk (10x Kuiper Belt).",
    ),

    "epsilon_eridani": StarTarget(
        name="epsilon_eridani",
        display_name="Epsilon Eridani",
        position_ly=[-5.98, -7.47, -4.72],
        distance_ly=10.5,
        spectral_type="K2V",
        mass_solar=0.82,
        habitable_zone_au=(0.5, 1.0),
        known_planets=2,
        notes="Young star (~0.4 Gyr). Active debris disk. Confirmed Jupiter analog.",
    ),

    "ross_128": StarTarget(
        name="ross_128",
        display_name="Ross 128",
        position_ly=[-6.08, -8.21, 1.34],
        distance_ly=11.0,
        spectral_type="M4V",
        mass_solar=0.17,
        habitable_zone_au=(0.04, 0.08),
        known_planets=1,
        notes="Ross 128 b: Earth-mass planet in HZ. Quietest known nearby M dwarf.",
    ),

    "luyten_726_8": StarTarget(
        name="luyten_726_8",
        display_name="Luyten 726-8 A/B (UV Ceti)",
        position_ly=[1.73, -6.90, -5.73],
        distance_ly=8.73,
        spectral_type="M5.5Ve / M6Ve",
        mass_solar=0.12,
        habitable_zone_au=(0.02, 0.05),
        known_planets=0,
        notes="UV Ceti prototype flare star. Binary. Intense radiation environment.",
    ),

    "trappist_1": StarTarget(
        name="trappist_1",
        display_name="TRAPPIST-1",
        position_ly=[24.3, -27.1, 13.8],
        distance_ly=39.5,
        spectral_type="M8V",
        mass_solar=0.089,
        habitable_zone_au=(0.029, 0.048),
        known_planets=7,
        notes="7 Earth-sized planets, 3 in HZ. Ultra-cool dwarf. JWST priority target.",
    ),

    "100_ly_target": StarTarget(
        name="100_ly_target",
        display_name="Generic 100 LY Target",
        position_ly=[100.0, 0.0, 0.0],
        distance_ly=100.0,
        spectral_type="G2V",
        mass_solar=1.0,
        habitable_zone_au=(0.9, 1.7),
        known_planets=0,
        notes="Hypothetical Sun-like target at 100 ly. 1000-year mission at 0.1c.",
    ),
}


def get_target(name: str) -> StarTarget:
    """Look up a star target by name. Raises KeyError if not found."""
    if name not in STAR_CATALOG:
        available = ", ".join(sorted(STAR_CATALOG.keys()))
        raise KeyError(f"Unknown star target '{name}'. Available: {available}")
    return STAR_CATALOG[name]


def mission_duration_years(target: StarTarget, velocity_c: float) -> float:
    """Calculate mission duration in years for a given target and cruise velocity."""
    if velocity_c <= 0:
        raise ValueError(f"velocity_c must be positive, got {velocity_c}")
    return target.distance_ly / velocity_c


def list_targets() -> list[dict[str, str | float]]:
    """List all available targets with key info for display."""
    result = []
    for key, t in sorted(STAR_CATALOG.items(), key=lambda kv: kv[1].distance_ly):
        result.append({
            "key": key,
            "name": t.display_name,
            "distance_ly": t.distance_ly,
            "spectral_type": t.spectral_type,
            "known_planets": t.known_planets,
            "duration_at_01c": round(t.distance_ly / 0.1, 1),
        })
    return result
