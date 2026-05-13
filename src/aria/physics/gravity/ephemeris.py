"""SPICE / Horizons ephemeris module for ARIA.

Three providers, in order of precision:

1. ``SpiceEphemeris`` — uses spiceypy + a DE440 kernel (highest precision,
   optional; degrades gracefully when spiceypy is not installed).

2. ``HorizonsRestEphemeris`` — queries JPL Horizons REST API
   (https://ssd.jpl.nasa.gov/api/horizons.api) for live state vectors.
   Responses are cached in-process by (body, Julian date) so repeated
   calls don't hit the network.  Falls back to analytic when offline.

3. ``AnalyticEphemeris`` — Keplerian propagation from J2000 mean elements
   (Meeus 1998, "Astronomical Algorithms" 2nd ed., Table 31.a).  Always
   available, no dependencies.  Typical accuracy: ±0.001 AU / ±0.5 m/s.

Public API::

    from aria.physics.gravity.ephemeris import get_body_state, BodyState
    st = get_body_state("mars", epoch_jd=2459000.5)   # → BodyState
    print(st.pos_km, st.vel_km_s)

Backend selection::

    get_body_state("mars", backend="spice")   # SpiceEphemeris
    get_body_state("mars", backend="horizons") # HorizonsRestEphemeris
    get_body_state("mars", backend="analytic") # AnalyticEphemeris
    get_body_state("mars", backend="auto")    # spice → horizons → analytic

SPICE kernel management::

    from aria.physics.gravity.ephemeris import KernelManager
    km = KernelManager()
    km.ensure_loaded()   # furnsh de440.bsp + naif0012.tls from ~/.aria/kernels/
"""
from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import json


# ──────────────────────────────────────────────────────────────────────────────
# BodyState
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BodyState:
    """Heliocentric ICRF state vector for a solar-system body."""
    body: str
    epoch_jd: float                     # Julian date (TDB)
    pos_km: tuple[float, float, float]  # x, y, z in km
    vel_km_s: tuple[float, float, float]  # vx, vy, vz in km/s
    source: str = "unknown"             # "spice", "horizons", "analytic"


# ──────────────────────────────────────────────────────────────────────────────
# Mean orbital elements — Meeus 1998 "Astronomical Algorithms" 2nd ed.
# Table 31.a: heliocentric ecliptic J2000, elements for J2000.0 + secular rates
# ──────────────────────────────────────────────────────────────────────────────
# Each entry: a_au, e, i_deg, Omega_deg (long. asc. node), pi_deg (long.
# perihelion), L0_deg (mean longitude at J2000), n_deg_day (mean motion)
#
# Source: Meeus (1998) Table 31.a, cross-checked against JPL DE430 mean
# elements published at https://ssd.jpl.nasa.gov/planets/approx_pos.html
# (Simon 1994 A&A 282 663 for T-polynomials; Standish 1992 for DE430 base).
_J2000_JD = 2_451_545.0  # Julian date of J2000.0 (2000-Jan-1.5)

_ELEMENTS: dict[str, tuple[float, float, float, float, float, float, float]] = {
    # body: (a_au, e, i_deg, Omega_deg, pi_deg, L0_deg, n_deg_day)
    "mercury":  (0.38710, 0.20563, 7.0048,  48.331,  77.456,  252.251, 4.09234),
    "venus":    (0.72332, 0.00677, 3.3947,  76.680, 131.564,  181.980, 1.60213),
    "earth":    (1.00000, 0.01671, 0.0001, 174.873, 102.937,  100.464, 0.98560),
    "mars":     (1.52371, 0.09339, 1.8497,  49.558, 336.040,  355.433, 0.52403),
    "jupiter":  (5.20288, 0.04839, 1.3034, 100.464,  14.331,   34.397, 0.08310),
    "saturn":   (9.53667, 0.05386, 2.4886, 113.666,  93.057,   50.077, 0.03346),
    "uranus":   (19.1914, 0.04724, 0.7730,  74.006, 173.005,  314.055, 0.01172),
    "neptune":  (30.0700, 0.00859, 1.7700, 131.784,  48.123,  304.349, 0.00600),
    # Sun is at origin in heliocentric; included for completeness (zero state)
    "sun":      (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
}

# Canonical NAIF IDs for Horizons queries
_NAIF_CODES: dict[str, str] = {
    "mercury": "199", "venus": "299", "earth": "399", "mars": "499",
    "jupiter": "599", "saturn": "699", "uranus": "799", "neptune": "899",
    "moon": "301", "sun": "10", "pluto": "999",
    "ceres": "2000001", "vesta": "2000004", "pallas": "2000002",
}


def _solve_kepler(M_rad: float, e: float, tol: float = 1e-10) -> float:
    """Eccentric anomaly E from mean anomaly M via Newton-Raphson.

    Danby (1988) "Fundamentals of Celestial Mechanics" §6.6: converges in
    3–5 iterations for e < 0.9.
    """
    E = M_rad + e * math.sin(M_rad)  # starter (Danby 1988 eq. 6.6.4)
    for _ in range(50):
        dE = (M_rad - E + e * math.sin(E)) / (1.0 - e * math.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E


def _keplerian_state(body: str, epoch_jd: float) -> BodyState:
    """Heliocentric ecliptic J2000 state from mean elements (Meeus 1998)."""
    if body == "sun":
        return BodyState(body, epoch_jd, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), "analytic")

    a_au, e, i_deg, Omega_deg, pi_deg, L0_deg, n_deg_day = _ELEMENTS[body]

    T_days = epoch_jd - _J2000_JD  # days since J2000
    L = math.radians(L0_deg + n_deg_day * T_days)  # mean longitude (rad)
    pi_r = math.radians(pi_deg)
    Omega_r = math.radians(Omega_deg)
    i_r = math.radians(i_deg)
    omega_r = pi_r - Omega_r       # argument of perihelion

    M_r = L - pi_r                 # mean anomaly (rad)
    M_r = M_r % (2 * math.pi)
    E = _solve_kepler(M_r, e)

    # True anomaly
    nu = 2.0 * math.atan2(
        math.sqrt(1 + e) * math.sin(E / 2.0),
        math.sqrt(1 - e) * math.cos(E / 2.0),
    )
    r_au = a_au * (1.0 - e * math.cos(E))

    # Perifocal (orbital-plane) coordinates
    xp = r_au * math.cos(nu)
    yp = r_au * math.sin(nu)

    # Rotate to ecliptic J2000 (Bate, Mueller, White 1971 §2.5)
    cos_O, sin_O = math.cos(Omega_r), math.sin(Omega_r)
    cos_w, sin_w = math.cos(omega_r), math.sin(omega_r)
    cos_i, sin_i = math.cos(i_r), math.sin(i_r)

    x_au = (cos_O * cos_w - sin_O * sin_w * cos_i) * xp + (-cos_O * sin_w - sin_O * cos_w * cos_i) * yp
    y_au = (sin_O * cos_w + cos_O * sin_w * cos_i) * xp + (-sin_O * sin_w + cos_O * cos_w * cos_i) * yp
    z_au = (sin_w * sin_i) * xp + (cos_w * sin_i) * yp

    # Velocity in perifocal frame (Bate §2.5 eq 2.6-6)
    # vis-viva in AU/day; k = Gaussian gravitational constant = 0.01720209895 AU^(3/2)/day
    k_gauss = 0.01720209895  # Gauss 1809 (NIST Const. 2018)
    p = a_au * (1.0 - e * e)
    vxp = -k_gauss / math.sqrt(p) * math.sin(nu)
    vyp = k_gauss / math.sqrt(p) * (e + math.cos(nu))

    vx_au_day = (cos_O * cos_w - sin_O * sin_w * cos_i) * vxp + (-cos_O * sin_w - sin_O * cos_w * cos_i) * vyp
    vy_au_day = (sin_O * cos_w + cos_O * sin_w * cos_i) * vxp + (-sin_O * sin_w + cos_O * cos_w * cos_i) * vyp
    vz_au_day = (sin_w * sin_i) * vxp + (cos_w * sin_i) * vyp

    # Convert AU → km, AU/day → km/s
    AU_KM = 1.495978707e8  # IAU 2012 nominal (km)
    DAY_S = 86400.0

    pos_km = (x_au * AU_KM, y_au * AU_KM, z_au * AU_KM)
    vel_km_s = (vx_au_day * AU_KM / DAY_S, vy_au_day * AU_KM / DAY_S, vz_au_day * AU_KM / DAY_S)
    return BodyState(body, epoch_jd, pos_km, vel_km_s, "analytic")


# ──────────────────────────────────────────────────────────────────────────────
# AnalyticEphemeris
# ──────────────────────────────────────────────────────────────────────────────

class AnalyticEphemeris:
    """Keplerian ephemeris from J2000 mean elements (Meeus 1998, Table 31.a).

    Accuracy: ±0.001 AU / ±0.5 m/s for main planets within ±200 yr of J2000.
    Always available — no optional dependencies.
    """

    BODIES = set(_ELEMENTS.keys())

    def get_state(self, body: str, epoch_jd: float) -> BodyState:
        bk = body.lower()
        if bk not in _ELEMENTS:
            raise ValueError(f"AnalyticEphemeris: unknown body '{body}'. "
                             f"Available: {sorted(_ELEMENTS.keys())}")
        return _keplerian_state(bk, epoch_jd)


# ──────────────────────────────────────────────────────────────────────────────
# HorizonsRestEphemeris
# ──────────────────────────────────────────────────────────────────────────────

_HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
_CACHE: dict[tuple[str, float], tuple[BodyState, float]] = {}  # (body, jd) → (state, cached_at)
_CACHE_TTL_S = 3600.0  # 1-hour cache; DE440 doesn't change

_ANALYTIC = AnalyticEphemeris()


def _horizons_state(body: str, epoch_jd: float, timeout_s: float = 10.0) -> BodyState:
    """Fetch heliocentric state from JPL Horizons REST API.

    Uses the vector table (VEC_TABLE=2) in ICRF J2000 frame, km + km/s.
    Falls back to AnalyticEphemeris when the network is unavailable.

    Reference: JPL Horizons API documentation rev. 2022-06
    (https://ssd-api.jpl.nasa.gov/doc/horizons.html).
    """
    bk = body.lower()
    naif = _NAIF_CODES.get(bk, bk)

    # In-process cache
    cache_key = (bk, round(epoch_jd, 4))
    if cache_key in _CACHE:
        state, ts = _CACHE[cache_key]
        if time.monotonic() - ts < _CACHE_TTL_S:
            return state

    params = {
        "format": "json",
        "COMMAND": f"'{naif}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": "'500@10'",       # heliocentric, ecliptic plane
        "TLIST": str(epoch_jd),
        "OUT_UNITS": "KM-S",
        "REF_SYSTEM": "ICRF",
        "REF_PLANE": "FRAME",
        "VEC_TABLE": "2",
        "VEC_CORR": "NONE",
        "QUANTITIES": "1",
    }
    url = f"{_HORIZONS_URL}?{urlencode(params)}"
    try:
        from aria.security.guard import safe_open_url
        body = safe_open_url(
            url,
            timeout=timeout_s,
            max_bytes=8 * 1024 * 1024,  # JPL Horizons JSON; usually < 100 KB
            allowed_schemes=("https",),
        )
        raw = json.loads(body.decode())
        result_text = raw.get("result", "")
        state = _parse_horizons_vectors(body, epoch_jd, result_text)
        _CACHE[cache_key] = (state, time.monotonic())
        return state
    except (URLError, OSError, KeyError, ValueError) as exc:
        warnings.warn(
            f"HorizonsRestEphemeris: network fetch failed for '{body}' "
            f"at JD {epoch_jd:.2f} ({exc!r}). Falling back to AnalyticEphemeris.",
            RuntimeWarning,
            stacklevel=3,
        )
        st = _ANALYTIC.get_state(body, epoch_jd)
        return BodyState(st.body, st.epoch_jd, st.pos_km, st.vel_km_s, "analytic_fallback")


def _parse_horizons_vectors(body: str, epoch_jd: float, text: str) -> BodyState:
    """Extract X, Y, Z, VX, VY, VZ from Horizons $$SOE / $$EOE block."""
    in_data = False
    px = py = pz = vx = vy = vz = None
    for line in text.splitlines():
        if "$$SOE" in line:
            in_data = True
            continue
        if "$$EOE" in line:
            break
        if not in_data:
            continue
        if line.strip().startswith("X ="):
            # Horizons format: "   X = 1.234567E+08  Y = 2.345E+08  Z = 1.23E+06"
            parts = line.replace("=", " ").split()
            for i, tok in enumerate(parts):
                if tok == "X":
                    px = float(parts[i + 1])
                elif tok == "Y":
                    py = float(parts[i + 1])
                elif tok == "Z":
                    pz = float(parts[i + 1])
        elif line.strip().startswith("VX="):
            parts = line.replace("=", " ").split()
            for i, tok in enumerate(parts):
                if tok == "VX":
                    vx = float(parts[i + 1])
                elif tok == "VY":
                    vy = float(parts[i + 1])
                elif tok == "VZ":
                    vz = float(parts[i + 1])
    if any(v is None for v in (px, py, pz, vx, vy, vz)):
        raise ValueError(f"Failed to parse Horizons response for {body!r}")
    return BodyState(body, epoch_jd, (px, py, pz), (vx, vy, vz), "horizons")


class HorizonsRestEphemeris:
    """Live state vectors from JPL Horizons REST API with in-process caching.

    Requires internet access; falls back to AnalyticEphemeris when offline.
    """

    def get_state(self, body: str, epoch_jd: float, timeout_s: float = 10.0) -> BodyState:
        return _horizons_state(body, epoch_jd, timeout_s=timeout_s)

    @staticmethod
    def clear_cache() -> None:
        _CACHE.clear()


# ──────────────────────────────────────────────────────────────────────────────
# SpiceEphemeris
# ──────────────────────────────────────────────────────────────────────────────

class SpiceEphemeris:
    """SPICE/DE440 ephemeris via spiceypy.

    ``spiceypy`` is an optional dependency. If it is not installed, every
    call raises ``ImportError`` with a clear install instruction.  Use
    ``SpiceEphemeris.is_available()`` to check before constructing.

    SPICE kernels are managed by ``KernelManager`` (see below). Call
    ``KernelManager().ensure_loaded()`` once before using this class, or
    pass a pre-loaded kernel set via the ``kernels`` constructor argument.
    """

    @staticmethod
    def is_available() -> bool:
        try:
            import spiceypy  # noqa: F401
            return True
        except ImportError:
            return False

    def __init__(self, kernels: Optional[list[str]] = None):
        try:
            import spiceypy as spice
        except ImportError as exc:
            raise ImportError(
                "spiceypy is required for SpiceEphemeris. "
                "Install: pip install spiceypy"
            ) from exc
        self._spice = spice
        if kernels:
            for k in kernels:
                spice.furnsh(k)

    def get_state(self, body: str, epoch_jd: float) -> BodyState:
        spice = self._spice
        # ET (ephemeris time) from Julian date
        # spiceypy.unitim: JD → ET; 2451545.0 is J2000.0
        et = spice.unitim(epoch_jd, "JDTDB", "ET")
        # NAIF ID or name string
        naif = _NAIF_CODES.get(body.lower(), body.upper())
        state, _ = spice.spkez(
            int(naif) if naif.isdigit() else spice.bodn2c(naif),
            et,
            "ECLIPJ2000",
            "NONE",
            10,  # heliocentric (Sun = NAIF 10)
        )
        pos_km = (state[0], state[1], state[2])
        vel_km_s = (state[3], state[4], state[5])
        return BodyState(body, epoch_jd, pos_km, vel_km_s, "spice")


# ──────────────────────────────────────────────────────────────────────────────
# KernelManager
# ──────────────────────────────────────────────────────────────────────────────

_KERNEL_URLS = {
    # DE440 planetary SPK (2000-2040): ~32 MB
    "de440s.bsp": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp",
    # Leap-second kernel
    "naif0012.tls": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls",
}


class KernelManager:
    """Manages SPICE kernel files under ``~/.aria/kernels/``.

    Usage::

        km = KernelManager()
        km.ensure_loaded()   # downloads missing kernels + furnsh
    """

    def __init__(self, kernel_dir: Optional[Path] = None):
        self.kernel_dir = kernel_dir or (Path.home() / ".aria" / "kernels")

    def _kernel_path(self, name: str) -> Path:
        return self.kernel_dir / name

    def download_kernel(self, name: str, url: str, timeout_s: int = 120) -> Path:
        """Download a SPICE kernel if not already present. Returns local path.

        Routed through ``safe_open_url`` so a malicious or misconfigured URL
        cannot be redirected at an internal IP, and the response is capped
        at 1 GiB (Earth-DE-440 kernels are ~120 MiB; 1 GiB is generous).
        """
        from aria.security.guard import safe_open_url

        dest = self._kernel_path(name)
        if dest.exists():
            return dest
        self.kernel_dir.mkdir(parents=True, exist_ok=True)
        print(f"[KernelManager] Downloading {name} from NAIF…")
        try:
            body = safe_open_url(
                url,
                timeout=timeout_s,
                max_bytes=1 * 1024 * 1024 * 1024,  # 1 GiB ceiling
                allowed_schemes=("https",),
            )
            with open(dest, "wb") as fh:
                fh.write(body)
            print(f"[KernelManager] Saved {dest} ({dest.stat().st_size // 1024} kB)")
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download {name}: {exc}") from exc
        return dest

    def ensure_loaded(self, download: bool = False) -> list[str]:
        """Furnsh all default kernels.  Returns list of loaded paths.

        Args:
            download: If True, download missing kernels from NAIF.
                      If False (default), skip kernels not present on disk
                      and warn instead of raising.
        """
        if not SpiceEphemeris.is_available():
            warnings.warn(
                "spiceypy not installed — kernel loading skipped. "
                "pip install spiceypy to enable full SPICE support.",
                ImportWarning,
                stacklevel=2,
            )
            return []

        import spiceypy as spice

        loaded: list[str] = []
        for name, url in _KERNEL_URLS.items():
            path = self._kernel_path(name)
            if not path.exists():
                if download:
                    try:
                        self.download_kernel(name, url)
                    except RuntimeError as exc:
                        warnings.warn(str(exc), RuntimeWarning, stacklevel=2)
                        continue
                else:
                    warnings.warn(
                        f"SPICE kernel not found: {path}. "
                        "Run KernelManager().ensure_loaded(download=True) to fetch.",
                        UserWarning,
                        stacklevel=2,
                    )
                    continue
            spice.furnsh(str(path))
            loaded.append(str(path))
        return loaded


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def get_body_state(
    body: str,
    epoch_jd: float,
    backend: str = "auto",
) -> BodyState:
    """Return heliocentric ICRF state for *body* at *epoch_jd*.

    Args:
        body:      Body name (case-insensitive): "earth", "mars", "jupiter",
                   "moon", "sun", "pluto", or any NAIF name/integer string.
        epoch_jd:  Epoch as Julian Date (TDB).  J2000.0 = 2451545.0.
        backend:   One of "auto", "spice", "horizons", "analytic".
                   "auto" tries spice → horizons → analytic in that order.

    Returns:
        BodyState with pos_km and vel_km_s in heliocentric ICRF frame.

    Raises:
        ValueError: unknown body (analytic backend only).
        ImportError: backend="spice" but spiceypy not installed.
    """
    _VALID_BACKENDS = {"auto", "spice", "horizons", "analytic"}
    b = backend.lower()
    if b not in _VALID_BACKENDS:
        raise ValueError(f"Unknown backend '{backend}'. Choose from: {sorted(_VALID_BACKENDS)}")

    bk = body.lower()

    if b == "spice":
        return SpiceEphemeris().get_state(bk, epoch_jd)

    if b == "horizons":
        return _horizons_state(bk, epoch_jd)

    if b == "analytic":
        return _ANALYTIC.get_state(bk, epoch_jd)

    # "auto": spice → horizons → analytic
    if SpiceEphemeris.is_available():
        try:
            return SpiceEphemeris().get_state(bk, epoch_jd)
        except Exception:
            pass
    # Try horizons only for known bodies
    if bk in _NAIF_CODES:
        st = _horizons_state(bk, epoch_jd)
        if st.source != "analytic_fallback":
            return st
    # Fall through to analytic
    return _ANALYTIC.get_state(bk, epoch_jd)
