"""Notable exoplanet host systems — curated subset of NASA Exoplanet Archive.

Focus on systems an amateur could identify in the sky with the ARIA
planetarium: bright host stars (mag ≤ ~8) plus historically important
discoveries (first exoplanet, first Earth-size, nearest terrestrial,
first directly imaged, etc.).

Data fields:
  name          — host star common name / catalog id
  hip_id        — Hipparcos number where available (for star_field lookup)
  ra, dec       — host J2000 coordinates (deg)
  distance_ly   — parsec → light years (× 3.26156)
  host_mag      — V magnitude of the host
  n_planets     — confirmed count at host
  discoverer    — Kepler/TESS/HARPS/Direct/etc.
  description   — short note about why it's famous

All values are public-domain astronomical fact (NASA Exoplanet Archive
is open-data, no copyrightable expression in coordinates/magnitudes).

Reference:
    NASA Exoplanet Archive — https://exoplanetarchive.ipac.caltech.edu/
    Akeson, R. et al. (2013) PASP 125:989 (archive design).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ExoplanetHost:
    name: str
    hip_id: int           # 0 if not in Hipparcos
    ra_deg: float         # J2000
    dec_deg: float        # J2000
    distance_ly: float
    host_mag: float
    n_planets: int
    discoverer: str
    description: str


# 40 notable exoplanet-hosting stars
EXOPLANET_HOSTS: List[ExoplanetHost] = [
    ExoplanetHost("51 Pegasi",          113357, 344.3666,  20.7686,   50.9,  5.49, 1, "Mayor & Queloz 1995",  "First exoplanet around a Sun-like star (Nobel 2019)"),
    ExoplanetHost("Upsilon Andromedae",  7513,   24.1993,  41.4053,   44.2,  4.09, 4, "Butler 1996+",         "First multi-planet main-sequence system"),
    ExoplanetHost("Tau Ceti",            8102,   26.0170, -15.9375,   11.9,  3.50, 4, "Tuomi 2012",           "Sun-like neighbor with candidates in habitable zone"),
    ExoplanetHost("Epsilon Eridani",    16537,   53.2327,  -9.4582,   10.5,  3.73, 1, "Hatzes 2000",          "Third-nearest exoplanet system; young K2V dwarf"),
    ExoplanetHost("Gliese 581",         74995,  229.8621,  -7.7217,   20.4, 10.56, 3, "Bonfils 2005",         "Red-dwarf system with rocky worlds in HZ"),
    ExoplanetHost("Gliese 667C",             0, 259.7487, -34.9959,   23.6, 10.22, 3, "Anglada-Escude 2013",  "Triple-star M-dwarf with HZ super-Earths"),
    ExoplanetHost("Proxima Centauri",   70890,  217.4290, -62.6795,    4.24,11.13, 3, "Anglada-Escude 2016",  "Nearest known exoplanet — Proxima b in HZ"),
    ExoplanetHost("Alpha Centauri B",   71681,  219.8960, -60.8381,    4.37, 1.35, 1, "Dumusque 2012*",       "Nearest Sun-like star; planet confirmation debated"),
    ExoplanetHost("Ross 128",           57548,  176.9405,   0.7996,   11.0, 11.12, 1, "Bonfils 2017",         "Quiet red dwarf with temperate rocky planet"),
    ExoplanetHost("Wolf 1061",          80824,  247.5651, -12.6610,   13.8, 10.07, 3, "Wright 2015",          "Nearby K-dwarf trio, middle planet near HZ"),
    ExoplanetHost("TRAPPIST-1",              0,  346.6200,  -5.0414,   40.7, 18.80, 7, "Gillon 2017",          "Seven Earth-size planets; 3-4 in habitable zone"),
    ExoplanetHost("Kepler-186",              0,  298.2833,  43.9561,  582,   14.62, 5, "Quintana 2014",        "First Earth-size planet in HZ of any star"),
    ExoplanetHost("Kepler-452",              0,  292.4020,  44.2771, 1799,   13.40, 1, "Jenkins 2015",         "\"Earth's bigger older cousin\" G2V host"),
    ExoplanetHost("Kepler-22",               0,  290.8333,  47.8833,  638,   11.66, 1, "Borucki 2012",         "First HZ planet confirmed by Kepler"),
    ExoplanetHost("Kepler-16",               0,  289.0807,  51.7574,  245,   11.80, 1, "Doyle 2011",           "First circumbinary planet (\"Tatooine\")"),
    ExoplanetHost("Kepler-90",               0,  284.4267,  49.3056, 2545,   14.00, 8, "Shallue 2017",         "Eight-planet system (tied with Solar System)"),
    ExoplanetHost("Kepler-11",               0,  297.1158,  41.9091, 2154,   13.80, 6, "Lissauer 2011",        "Six compact planets, all tightly packed"),
    ExoplanetHost("K2-18",                   0,  172.5604,   7.5879,  124,   13.48, 2, "Montet 2015",          "Hycean candidate with DMS detection (JWST 2023)"),
    ExoplanetHost("HD 189733",          98505,  300.1822,  22.7101,   64.5,  7.67, 1, "Bouchy 2005",          "Transiting hot-Jupiter, blue planet (scattering)"),
    ExoplanetHost("HD 209458",         108859,  330.7950,  18.8842,  159,   7.65, 1, "Charbonneau 2000",      "First transiting exoplanet discovered"),
    ExoplanetHost("HD 80606",           45982,  140.6574,  50.6037,  216,   9.00, 1, "Naef 2001",            "Extreme eccentric orbit (e=0.93)"),
    ExoplanetHost("WASP-12",                 0,   97.6366,  29.6725, 1369,   11.57, 1, "Hebb 2009",           "Ultra-hot Jupiter being tidally shredded"),
    ExoplanetHost("WASP-33",                 0,   36.7154,  37.5506,  400,   8.30, 1, "Cameron 2010",        "Fast-rotating host; first SX Phe-like variable pulsation"),
    ExoplanetHost("WASP-96",                 0,    1.0617, -47.3619,  960,  12.20, 1, "Hellier 2014",        "JWST first atmospheric spectrum (NIRISS, 2022)"),
    ExoplanetHost("GJ 1214",                 0,  258.8300,   4.9589,   47.5,14.71, 1, "Charbonneau 2009",     "Waterworld / mini-Neptune atmosphere"),
    ExoplanetHost("GJ 436",                 57087, 175.5464,  26.7064,   32.6, 10.67, 1, "Butler 2004",          "Hot Neptune with evaporating exosphere"),
    ExoplanetHost("LHS 1140",                0,   16.4133, -15.2686,   48.6, 14.20, 2, "Dittmann 2017",        "Dense super-Earth in HZ around an M dwarf"),
    ExoplanetHost("TOI-700",                 0,  104.5500, -65.5889,  101.4, 13.10, 4, "Gilbert 2020",         "First TESS-found Earth-size HZ planet"),
    ExoplanetHost("Tau Boötis",         67275,  206.8154,  17.4567,   50.9,  4.50, 1, "Butler 1997",          "Hot Jupiter around naked-eye F-dwarf"),
    ExoplanetHost("Gamma Cephei A",    116727,  354.8362,  77.6327,   45.0,  3.22, 1, "Campbell 1988",        "Among the first exoplanet candidates (binary host)"),
    ExoplanetHost("Fomalhaut",         113368,  344.4126, -29.6222,   25.1,  1.16, 1, "Kalas 2008*",          "First directly-imaged candidate (disk)"),
    ExoplanetHost("Pollux",             37826,  116.3287,  28.0262,   34.0,  1.14, 1, "Hatzes 2006",          "Closest known giant-planet host (K giant)"),
    ExoplanetHost("HR 8799",           114189,  346.8701,  21.1339,  129,   5.96, 4, "Marois 2008",          "First directly-imaged planetary system (4 gas giants)"),
    ExoplanetHost("Beta Pictoris",      27321,   86.8211, -51.0666,   63.4,  3.86, 2, "Lagrange 2009",        "Directly-imaged β Pic b in young debris disk"),
    ExoplanetHost("2M1207",                  0,  181.9262, -39.3917,  172,  19.00, 1, "Chauvin 2004",         "First image of a planetary-mass companion"),
    ExoplanetHost("55 Cancri",          43587,  133.1493,  28.3317,   40.3,  5.96, 5, "Butler 1997",          "Five-planet system around bright sun-like star"),
    ExoplanetHost("HD 10180",             7599,   24.8953, -60.5156,  127,   7.33, 6, "Lovis 2011",           "Seven candidate planets; possibly 9 total"),
    ExoplanetHost("HD 219134",         114622,  348.3208,  57.1683,   21.3,  5.57, 6, "Motalebi 2015",        "Nearby rocky system visible to naked eye"),
    ExoplanetHost("HD 40307",           27887,   88.6850, -60.0179,   42.0,  7.17, 6, "Mayor 2008",           "Six super-Earths including HZ candidate"),
    ExoplanetHost("HIP 65426",          65426,  200.9987, -51.5041,  385,   7.07, 1, "Chauvin 2017",         "SPHERE-imaged gas giant around young A-star"),
]


# ════════════════════════════════════════════════════════════════════
#  Lookups
# ════════════════════════════════════════════════════════════════════

def bright_hosts(mag_limit: float = 6.5) -> List[ExoplanetHost]:
    """Hosts visible to the naked eye (V ≤ mag_limit)."""
    return [h for h in EXOPLANET_HOSTS if h.host_mag <= mag_limit]


def above_horizon(hosts: List[ExoplanetHost], jd_ut: float,
                  lat_deg: float, lon_deg: float,
                  min_alt_deg: float = 0.0) -> List[ExoplanetHost]:
    """Filter to hosts currently above the observer's horizon."""
    from aria.simulation.observer import (
        equatorial_to_horizontal, local_sidereal_time_deg,
    )
    lst = local_sidereal_time_deg(jd_ut, lon_deg)
    out: List[ExoplanetHost] = []
    for h in hosts:
        alt, _ = equatorial_to_horizontal(h.ra_deg, h.dec_deg, lst, lat_deg)
        if alt >= min_alt_deg:
            out.append(h)
    return out
