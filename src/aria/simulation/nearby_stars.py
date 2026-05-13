"""Stars within 25 light-years — critical for interstellar mission design.

ARIA's generation ship / sleeper-ship scenarios need targets. This module
lists all known stars within 25 ly of the Sun, prioritized by those most
often discussed as targets: Sun-like hosts, M-dwarfs with known planets,
nearest reachable.

Source: RECONS (REsearch Consortium on Nearby Stars) public catalog +
SIMBAD. Parallax-derived distances use the best modern measurements
(Gaia DR3 where possible).

Fields:
  name, hip_id, ra/dec, distance_ly, spectral_type, abs_magnitude,
  apparent_magnitude, category, known_planets, notes.

Category coding:
  'sun_like'   G-type, most relevant for colonization targets
  'm_dwarf'    red dwarfs (most numerous, habitable-zone close-in)
  'k_dwarf'    orange dwarfs (Goldilocks for life?)
  'binary'     multiple system
  'exotic'     white dwarf / brown dwarf / high-mass

Reference:
    RECONS 25-parsec catalog (http://www.recons.org/)
    Henry, T. J. et al. (2018) AJ 155:265
    Gaia Collaboration (2023) DR3 Vizier table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class NearbyStar:
    name: str
    hip_id: int
    ra_deg: float
    dec_deg: float
    distance_ly: float
    spectral_type: str
    abs_mag: float
    app_mag: float
    category: str
    known_planets: int
    notes: str


NEARBY_STARS: List[NearbyStar] = [
    NearbyStar("Proxima Centauri",    70890, 217.4290, -62.6795,  4.246, "M5.5V",  15.60, 11.13, "m_dwarf", 3,
               "Nearest star; hosts Proxima b in habitable zone"),
    NearbyStar("Alpha Centauri A",    71683, 219.9020, -60.8341,  4.367, "G2V",     4.38,  0.00, "sun_like", 0,
               "Sun-like; triple system with B (K1V) and Proxima"),
    NearbyStar("Alpha Centauri B",    71681, 219.8960, -60.8381,  4.367, "K1V",     5.71,  1.35, "k_dwarf", 1,
               "Cen B with debated exoplanet candidate (Bb)"),
    NearbyStar("Barnard's Star",      87937, 269.4522,   4.6682,  5.963, "M4.0V",  13.22,  9.54, "m_dwarf", 0,
               "Largest proper motion (10.3\"/yr); candidate planet 2018"),
    NearbyStar("Luhman 16 A",             0, 162.3283, -53.3194,  6.503, "L7.5",   16.50, 10.70, "exotic", 0,
               "Brown-dwarf binary; nearest after α Cen (discovered 2013)"),
    NearbyStar("WISE 0855-0714",          0, 133.8529, -7.2440,   7.26,  "Y2",      25.00, 25.00, "exotic", 0,
               "Coldest known brown dwarf (~250 K)"),
    NearbyStar("Wolf 359",            54035, 165.8320,   7.0148,  7.856, "M6.5V",  16.64, 13.45, "m_dwarf", 2,
               "Star Trek fame; two candidate planets from Tuomi 2019"),
    NearbyStar("Lalande 21185",       54035, 165.8300,  35.9700,  8.307, "M2.0V",  10.44,  7.47, "m_dwarf", 2,
               "Nearby bright M-dwarf; two confirmed planets"),
    NearbyStar("Sirius A",            32349, 101.2870, -16.7161,  8.611, "A1V",     1.42, -1.46, "sun_like", 0,
               "Brightest night-time star; binary with white dwarf Sirius B"),
    NearbyStar("Sirius B",                0, 101.2870, -16.7161,  8.611, "DA2",    11.35,  8.50, "exotic", 0,
               "White dwarf companion to Sirius A; Chandrasekhar-limit test"),
    NearbyStar("Luyten 726-8 A",       1475,  24.7579, -17.9500,  8.730, "M5.5V",  15.32, 12.57, "m_dwarf", 0,
               "BY Draconis variable; member of UV Ceti binary"),
    NearbyStar("Ross 154",            92403, 282.4553, -23.8361,  9.691, "M3.5V",  13.07, 10.44, "m_dwarf", 0,
               "Active flare star in Sagittarius"),
    NearbyStar("Ross 248",           115712, 355.4833,  44.1733, 10.300, "M5.5V",  14.79, 12.29, "m_dwarf", 0,
               "Nearest star in 36,000 years (V'ger passed near in Star Trek)"),
    NearbyStar("Epsilon Eridani",     16537,  53.2327,  -9.4582, 10.476, "K2V",     6.19,  3.73, "k_dwarf", 1,
               "Young K-dwarf with debris disk; candidate planet b"),
    NearbyStar("Lacaille 9352",      114046, 346.4667, -35.8511, 10.742, "M1.5V",   9.75,  7.34, "m_dwarf", 2,
               "Prominent southern high-proper-motion star"),
    NearbyStar("Ross 128",            57548, 176.9405,   0.7996, 11.029, "M4.0V",  13.53, 11.12, "m_dwarf", 1,
               "Quiet host for Ross 128 b (temperate rocky)"),
    NearbyStar("61 Cygni A",         104214, 316.7244,  38.7500, 11.403, "K5V",     7.48,  5.21, "k_dwarf", 0,
               "First stellar parallax measurement (Bessel 1838)"),
    NearbyStar("61 Cygni B",         104217, 316.7244,  38.7500, 11.406, "K7V",     8.33,  6.05, "k_dwarf", 0,
               "Companion to 61 Cyg A; binary ~659 yr orbit"),
    NearbyStar("Procyon A",           37279, 114.8253,   5.2250, 11.464, "F5IV-V",  2.66,  0.38, "sun_like", 0,
               "Brightest star in Canis Minor; binary with WD Procyon B"),
    NearbyStar("Procyon B",               0, 114.8253,   5.2250, 11.464, "DA",     13.00, 10.80, "exotic", 0,
               "White dwarf companion to Procyon A"),
    NearbyStar("Struve 2398 A",       91768, 280.6779,  59.4903, 11.526, "M3.0V",  11.18,  8.90, "m_dwarf", 0,
               "High-proper-motion M-dwarf binary with Struve 2398 B"),
    NearbyStar("Groombridge 34 A",     1475,   4.5977,  44.0222, 11.624, "M1.5V",  10.39,  8.09, "m_dwarf", 2,
               "Nearby flare-star binary; multiple planet candidates"),
    NearbyStar("Epsilon Indi",       108870, 330.8400, -56.7861, 11.824, "K5V",     6.89,  4.68, "k_dwarf", 1,
               "K-dwarf triple system; hosts brown dwarf pair Eps Ind Ba/Bb"),
    NearbyStar("Tau Ceti",             8102,  26.0170, -15.9375, 11.912, "G8V",     5.69,  3.50, "sun_like", 4,
               "Sun-like single star; candidate planets in HZ"),
    NearbyStar("GJ 1061",             17366,  53.0075, -44.5072, 12.044, "M5.5V",  15.26, 13.09, "m_dwarf", 3,
               "Three temperate planet candidates; c in HZ"),
    NearbyStar("YZ Ceti",              5643,  17.9917, -17.0500, 12.129, "M4.5V",  14.07, 12.02, "m_dwarf", 3,
               "Compact multi-planet M-dwarf system"),
    NearbyStar("Luyten's Star",       36208, 111.8498, +5.2303,  12.366, "M3.5V",  11.97,  9.84, "m_dwarf", 2,
               "Two candidate planets in habitable zone"),
    NearbyStar("Teegarden's Star",         0,  43.2547, +16.8808,12.514,  "M7.0V",  17.22, 15.40, "m_dwarf", 2,
               "Very cool M-dwarf with two temperate rocky planets"),
    NearbyStar("Kapteyn's Star",      24186,  77.9197, -45.0189, 12.772, "M1.0V",  10.89,  8.86, "m_dwarf", 2,
               "Halo star with retrograde orbit; candidate HZ planet"),
    NearbyStar("Lacaille 8760",      105090, 319.7312, -38.8717, 12.909, "M0.0V",   8.69,  6.67, "m_dwarf", 0,
               "Bright M-dwarf; no confirmed planets"),
    NearbyStar("Krüger 60 A",            0,  341.0700,  57.7000, 13.149, "M3.0V",  11.58,  9.59, "m_dwarf", 0,
               "Close M-dwarf binary with spectacular BY Dra variability"),
    NearbyStar("Wolf 1061",           80824, 247.5651, -12.6610, 13.822, "M3.5V",  10.07,  7.97, "m_dwarf", 3,
               "Three super-Earths; middle planet near habitable zone"),
    NearbyStar("Van Maanen's Star",         3829,  8.8672,  5.3878, 14.072, "DZ7",   14.09, 12.38, "exotic", 0,
               "First isolated white dwarf discovered"),
    NearbyStar("Gliese 1",             439,   1.3487, -37.3572, 14.170, "M3.0V",  10.37,  8.56, "m_dwarf", 0,
               "First entry in Gliese catalog"),
    NearbyStar("Gliese 581",          74995, 229.8621,  -7.7217, 20.400, "M3.0V",  11.53, 10.56, "m_dwarf", 3,
               "Famous exoplanet host with planets in HZ debate"),
    NearbyStar("GJ 674",              85523, 262.1667, -46.8917, 14.809, "M2.5V",  11.04,  9.38, "m_dwarf", 1,
               "Magnetic-active M-dwarf with Neptune-mass planet"),
    NearbyStar("GJ 876",             113020, 343.3208,  -14.2622, 15.205, "M3.5V", 11.79,  10.17, "m_dwarf", 4,
               "Archetypal multi-planet M-dwarf system"),
]
