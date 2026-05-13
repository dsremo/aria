"""JPL Small-Body Database — Close-Approach + SBDB integration.

Two endpoints from NASA JPL Solar System Dynamics:

  * Close-Approach Data (CAD) — listed asteroids/comets that pass
    within a configurable distance of Earth (or any body) inside a
    date window. Drives ARIA's planetary-defense conjunction layer.
    https://ssd-api.jpl.nasa.gov/doc/cad.html

  * Small-Body Database (SBDB) — orbital elements + physical
    parameters for any named small body. Used to build full
    state vectors for high-fidelity conjunction screening.
    https://ssd-api.jpl.nasa.gov/doc/sbdb.html

The JPL APIs are public, no authentication, no documented rate
limit — but ARIA caches responses locally with a configurable
TTL out of courtesy and to keep CI deterministic.

Related ARIA layers:
  * aria.conjunction.* — KD-tree screening + Foster/Chan/MC Pc
  * aria.products.conjunction_screener — multi-tenant HTTPS API
  * aria.simulation.small_bodies — existing solar-system
    catalog (25 asteroids + 16 comets, parametric)

This module BRIDGES the live JPL feed into ARIA's existing
conjunction stack — it does NOT duplicate the orbital-mechanics
layers.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib import error, parse, request

import structlog

logger = structlog.get_logger()


JPL_BASE_URL = "https://ssd-api.jpl.nasa.gov"
DEFAULT_CACHE_TTL_S = 3600.0          # 1 h — close-approach data is slow-moving
DEFAULT_REQUEST_TIMEOUT_S = 10.0
MAX_DATE_WINDOW_DAYS = 36525          # JPL CAD upper bound (100 years)


# ── Data classes ────────────────────────────────────────────────


@dataclass(frozen=True)
class CloseApproach:
    """One asteroid/comet close-approach event.

    All units mirror the JPL CAD schema:
      * dist_au — nominal close-approach distance (AU)
      * v_rel_kmps — relative velocity at TCA (km/s)
      * h_mag — absolute magnitude (proxy for size; smaller = brighter = larger)
      * jd_tca — Julian date of close approach
    """

    designation: str               # e.g. "2023 BU", "(99942) Apophis"
    body: str                      # close-approach target (default "Earth")
    cd_tca: str                    # human-readable calendar date of TCA
    jd_tca: float                  # Julian date of TCA
    dist_au: float                 # nominal close-approach distance (AU)
    dist_min_au: float             # 3-σ minimum
    dist_max_au: float             # 3-σ maximum
    v_rel_kmps: float              # relative velocity (km/s)
    v_inf_kmps: float              # hyperbolic excess velocity (km/s)
    h_mag: Optional[float]         # absolute magnitude (None if unknown)
    orbit_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SmallBody:
    """Orbital + physical summary of one small body."""

    designation: str
    full_name: str
    spk_id: Optional[int]            # SPICE NAIF ID
    epoch_jd: float                  # Osculating epoch
    semi_major_axis_au: float        # a
    eccentricity: float              # e
    inclination_deg: float           # i
    longitude_node_deg: float        # Ω
    argument_perihelion_deg: float   # ω
    mean_anomaly_deg: float          # M
    h_mag: Optional[float]
    diameter_km: Optional[float]
    rotation_period_h: Optional[float]
    pha: bool = False                # Potentially-Hazardous Asteroid?
    neo: bool = False                # Near-Earth Object?

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Client ──────────────────────────────────────────────────────


@dataclass
class JplSbdbClient:
    """Cached client for the JPL SBDB + CAD endpoints.

    File-cache layout: ``<cache_dir>/<endpoint>/<query-sha>.json``.
    """

    cache_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("ARIA_RUNTIME_DIR", "data/runtime")
    ) / "jpl_sbdb_cache")
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S
    user_agent: str = "ARIA-Core/1.0 (autonomy@aria-core.dev)"
    base_url: str = JPL_BASE_URL

    # ── Cache plumbing ─────────────────────────────────────────

    def _cache_path(self, endpoint: str, query_key: str) -> Path:
        # Filesystem-safe filename for any URL-encoded query.
        endpoint_clean = endpoint.strip("/").replace("/", "_") or "root"
        safe = parse.quote(query_key, safe="")
        return self.cache_dir / endpoint_clean / f"{safe}.json"

    def _read_cache(self, endpoint: str, query_key: str) -> Optional[Dict[str, Any]]:
        path = self._cache_path(endpoint, query_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "jpl.cache_read_failed", path=str(path), error=str(exc),
            )
            return None
        cached_at = float(payload.get("_cached_at", 0.0))
        if (time.time() - cached_at) > self.cache_ttl_s:
            return None
        return payload

    def _write_cache(
        self, endpoint: str, query_key: str, payload: Dict[str, Any],
    ) -> None:
        try:
            path = self._cache_path(endpoint, query_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload_with_ts = dict(payload)
            payload_with_ts["_cached_at"] = time.time()
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload_with_ts), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("jpl.cache_write_failed", error=str(exc))

    # ── Core HTTP ──────────────────────────────────────────────

    def _fetch_raw(
        self, endpoint: str, params: Dict[str, Any],
    ) -> Dict[str, Any]:
        query = parse.urlencode(params)
        url = f"{self.base_url}{endpoint}?{query}"
        req = request.Request(
            url, headers={"User-Agent": self.user_agent}, method="GET",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"JPL returned HTTP {response.status} for {endpoint}"
                    )
                body = response.read()
        except error.HTTPError as exc:
            raise RuntimeError(f"JPL HTTP {exc.code}: {exc.reason}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"JPL network error: {exc.reason}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"JPL returned non-JSON: {exc}") from exc

    # ── CAD: close-approach data ───────────────────────────────

    def close_approaches(
        self,
        date_min: str = "now",
        date_max: str = "+60",
        body: str = "Earth",
        dist_max_au: float = 0.05,
        neo_only: bool = True,
    ) -> List[CloseApproach]:
        """Return close approaches in [date_min, date_max] within
        ``dist_max_au`` of ``body``.

        ``date_max`` accepts either ISO date or ``+D`` for D days from
        now (max ~100 years per JPL upper bound).
        """
        params: Dict[str, Any] = {
            "date-min": date_min,
            "date-max": date_max,
            "body": body,
            "dist-max": dist_max_au,
            "sort": "date",
        }
        if neo_only:
            params["neo"] = "true"

        endpoint = "/cad.api"
        query_key = parse.urlencode(params)
        cached = self._read_cache(endpoint, query_key)
        payload = cached or self._fetch_raw(endpoint, params)
        if cached is None:
            self._write_cache(endpoint, query_key, payload)

        return self._parse_cad(payload)

    @staticmethod
    def _parse_cad(payload: Dict[str, Any]) -> List[CloseApproach]:
        if not isinstance(payload.get("data"), list):
            return []
        fields = payload.get("fields", [])
        if not fields:
            return []
        idx = {field_name: i for i, field_name in enumerate(fields)}
        out: List[CloseApproach] = []
        for row in payload["data"]:
            try:
                out.append(CloseApproach(
                    designation=str(row[idx["des"]]),
                    body=str(row[idx.get("body", -1)]) if "body" in idx else "Earth",
                    cd_tca=str(row[idx["cd"]]),
                    jd_tca=float(row[idx["jd"]]),
                    dist_au=float(row[idx["dist"]]),
                    dist_min_au=float(row[idx["dist_min"]]),
                    dist_max_au=float(row[idx["dist_max"]]),
                    v_rel_kmps=float(row[idx["v_rel"]]),
                    v_inf_kmps=float(row[idx["v_inf"]]),
                    h_mag=_safe_float(row[idx["h"]]) if "h" in idx else None,
                    orbit_id=(
                        str(row[idx["orbit_id"]]) if "orbit_id" in idx else None
                    ),
                ))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                logger.warning("jpl.cad_parse_failed", error=str(exc))
        return out

    # ── SBDB: per-body orbital elements ────────────────────────

    def lookup(self, designation: str) -> Optional[SmallBody]:
        """Fetch orbital elements + physical params for one small body.

        ``designation`` accepts SPK-ID, MPC packed designation, or full
        name (e.g. "Apophis", "99942", "2004 MN4").
        """
        params = {"sstr": designation, "phys-par": "true"}
        endpoint = "/sbdb.api"
        query_key = parse.urlencode(params)
        cached = self._read_cache(endpoint, query_key)
        payload = cached or self._fetch_raw(endpoint, params)
        if cached is None:
            self._write_cache(endpoint, query_key, payload)
        return self._parse_sbdb(payload)

    @staticmethod
    def _parse_sbdb(payload: Dict[str, Any]) -> Optional[SmallBody]:
        if "object" not in payload:
            return None
        obj = payload["object"]
        orbit = payload.get("orbit", {})
        elements = {e["name"]: e["value"] for e in orbit.get("elements", [])
                    if isinstance(e, dict) and "name" in e and "value" in e}
        # Physical parameters block — optional, may be absent.
        phys_params = {
            p["name"]: p.get("value")
            for p in payload.get("phys_par", [])
            if isinstance(p, dict) and "name" in p
        }

        try:
            return SmallBody(
                designation=str(obj.get("des", "")),
                full_name=str(obj.get("fullname", obj.get("des", ""))),
                spk_id=int(obj["spkid"]) if obj.get("spkid") else None,
                epoch_jd=_safe_float(orbit.get("epoch")) or 0.0,
                semi_major_axis_au=_safe_float(elements.get("a")) or 0.0,
                eccentricity=_safe_float(elements.get("e")) or 0.0,
                inclination_deg=_safe_float(elements.get("i")) or 0.0,
                longitude_node_deg=_safe_float(elements.get("om")) or 0.0,
                argument_perihelion_deg=_safe_float(elements.get("w")) or 0.0,
                mean_anomaly_deg=_safe_float(elements.get("ma")) or 0.0,
                h_mag=_safe_float(phys_params.get("H")),
                diameter_km=_safe_float(phys_params.get("diameter")),
                rotation_period_h=_safe_float(phys_params.get("rot_per")),
                pha=bool(obj.get("pha", False)),
                neo=bool(obj.get("neo", False)),
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "jpl.sbdb_parse_failed",
                designation=obj.get("des"),
                error=str(exc),
            )
            return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Module singleton ─────────────────────────────────────────────


_INSTANCE: Optional[JplSbdbClient] = None


def get_jpl_sbdb_client() -> JplSbdbClient:
    """Process-wide JPL SBDB client."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = JplSbdbClient()
    return _INSTANCE


def reset_for_test() -> None:
    """Test-only — replace the singleton with a fresh instance."""
    global _INSTANCE
    _INSTANCE = None
