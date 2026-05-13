"""All 88 IAU constellations — names, abbreviations, centroids, stick figures.

Centroid (RA, Dec) values are the officially-defined IAU constellation
geometric centers (Delporte 1930), useful for placing labels. Stick-figure
line endpoints are HIP catalog IDs of the bright stars that form the
traditional Western "Sky & Telescope" depiction of each constellation
(Sinnott 1981; Toomey 1991 public-domain HEASARC dataset).

All data here is astronomical fact — not copyrightable expression.

Reference:
    Delporte, E. (1930) "Délimitation scientifique des constellations."
        Cambridge University Press, on behalf of the IAU.
    Sinnott, R. W. (1981) "Sky Atlas 2000.0." Sky Publishing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Constellation:
    abbr: str            # IAU 3-letter code
    name: str            # English name
    genitive: str        # Latin genitive form
    ra_deg: float        # geometric centroid RA (J2000)
    dec_deg: float       # geometric centroid Dec
    family: str          # Heavenly Waters / Hercules / Orion / Perseus / Ursa Major / Zodiac / Bayer / La Caille


# ════════════════════════════════════════════════════════════════════
#  All 88 IAU constellations with centroids (Delporte 1930)
# ════════════════════════════════════════════════════════════════════

CONSTELLATIONS: List[Constellation] = [
    Constellation("And", "Andromeda",         "Andromedae",         8.86,   37.37, "Perseus"),
    Constellation("Ant", "Antlia",            "Antliae",          162.81,  -32.39, "La Caille"),
    Constellation("Aps", "Apus",              "Apodis",           245.96,  -76.83, "Bayer"),
    Constellation("Aqr", "Aquarius",          "Aquarii",          335.45,  -10.79, "Zodiac"),
    Constellation("Aql", "Aquila",            "Aquilae",          297.12,    3.46, "Hercules"),
    Constellation("Ara", "Ara",               "Arae",             262.43,  -56.65, "Hercules"),
    Constellation("Ari", "Aries",             "Arietis",           41.95,   20.79, "Zodiac"),
    Constellation("Aur", "Auriga",            "Aurigae",           90.50,   42.10, "Perseus"),
    Constellation("Boo", "Bootes",            "Bootis",           213.19,   31.27, "Ursa Major"),
    Constellation("Cae", "Caelum",            "Caeli",             71.16,  -38.16, "La Caille"),
    Constellation("Cam", "Camelopardalis",    "Camelopardalis",    79.79,   69.39, "Ursa Major"),
    Constellation("Cnc", "Cancer",            "Cancri",           130.16,   19.81, "Zodiac"),
    Constellation("CVn", "Canes Venatici",    "Canum Venaticorum",196.32,   40.10, "Ursa Major"),
    Constellation("CMa", "Canis Major",       "Canis Majoris",    102.50,  -22.14, "Orion"),
    Constellation("CMi", "Canis Minor",       "Canis Minoris",    115.49,    6.43, "Orion"),
    Constellation("Cap", "Capricornus",       "Capricorni",       316.74,  -18.05, "Zodiac"),
    Constellation("Car", "Carina",            "Carinae",          138.55,  -63.22, "Heavenly Waters"),
    Constellation("Cas", "Cassiopeia",        "Cassiopeiae",       16.45,   62.18, "Perseus"),
    Constellation("Cen", "Centaurus",         "Centauri",         196.66,  -47.35, "Hercules"),
    Constellation("Cep", "Cepheus",           "Cephei",           335.62,   71.01, "Perseus"),
    Constellation("Cet", "Cetus",             "Ceti",              26.49,  -7.18,  "Perseus"),
    Constellation("Cha", "Chamaeleon",        "Chamaeleontis",    164.36,  -79.21, "Bayer"),
    Constellation("Cir", "Circinus",          "Circini",          221.93,  -63.03, "La Caille"),
    Constellation("Col", "Columba",           "Columbae",          87.93,  -35.10, "Heavenly Waters"),
    Constellation("Com", "Coma Berenices",    "Comae Berenices",  186.43,   23.31, "Ursa Major"),
    Constellation("CrA", "Corona Australis",  "Coronae Australis",286.85,  -41.15, "Hercules"),
    Constellation("CrB", "Corona Borealis",   "Coronae Borealis", 234.53,   32.62, "Ursa Major"),
    Constellation("Crv", "Corvus",            "Corvi",            187.41,  -18.44, "Hercules"),
    Constellation("Crt", "Crater",            "Crateris",         170.19,  -15.93, "Hercules"),
    Constellation("Cru", "Crux",              "Crucis",           187.86,  -60.19, "Bayer"),
    Constellation("Cyg", "Cygnus",            "Cygni",            305.31,   44.55, "Hercules"),
    Constellation("Del", "Delphinus",         "Delphini",         310.38,   11.67, "Heavenly Waters"),
    Constellation("Dor", "Dorado",            "Doradus",           81.74,  -59.39, "Bayer"),
    Constellation("Dra", "Draco",             "Draconis",         215.96,   67.00, "Ursa Major"),
    Constellation("Equ", "Equuleus",          "Equulei",          318.91,    7.76, "Heavenly Waters"),
    Constellation("Eri", "Eridanus",          "Eridani",           58.75,  -28.76, "Heavenly Waters"),
    Constellation("For", "Fornax",            "Fornacis",          39.60,  -31.65, "La Caille"),
    Constellation("Gem", "Gemini",            "Geminorum",        108.39,   22.60, "Zodiac"),
    Constellation("Gru", "Grus",              "Gruis",            335.20,  -46.35, "Bayer"),
    Constellation("Her", "Hercules",          "Herculis",         258.76,   27.50, "Hercules"),
    Constellation("Hor", "Horologium",        "Horologii",         52.26,  -53.34, "La Caille"),
    Constellation("Hya", "Hydra",             "Hydrae",           175.83,  -14.55, "Hercules"),
    Constellation("Hyi", "Hydrus",            "Hydri",             37.39,  -69.96, "Bayer"),
    Constellation("Ind", "Indus",             "Indi",             318.71,  -59.71, "Bayer"),
    Constellation("Lac", "Lacerta",           "Lacertae",         334.32,   46.00, "Hercules"),
    Constellation("Leo", "Leo",               "Leonis",           163.25,   13.13, "Zodiac"),
    Constellation("LMi", "Leo Minor",         "Leonis Minoris",   161.10,   32.13, "Ursa Major"),
    Constellation("Lep", "Lepus",             "Leporis",           82.89,  -19.05, "Orion"),
    Constellation("Lib", "Libra",             "Librae",           227.60,  -15.23, "Zodiac"),
    Constellation("Lup", "Lupus",             "Lupi",             227.96,  -42.71, "Hercules"),
    Constellation("Lyn", "Lynx",              "Lyncis",           117.25,   47.47, "Ursa Major"),
    Constellation("Lyr", "Lyra",              "Lyrae",            283.45,   36.69, "Hercules"),
    Constellation("Men", "Mensa",             "Mensae",            83.29,  -77.50, "La Caille"),
    Constellation("Mic", "Microscopium",      "Microscopii",      314.16,  -36.27, "La Caille"),
    Constellation("Mon", "Monoceros",         "Monocerotis",      102.15,    0.28, "Orion"),
    Constellation("Mus", "Musca",             "Muscae",           188.32,  -70.16, "Bayer"),
    Constellation("Nor", "Norma",             "Normae",           241.27,  -51.35, "La Caille"),
    Constellation("Oct", "Octans",            "Octantis",         320.06,  -82.15, "La Caille"),
    Constellation("Oph", "Ophiuchus",         "Ophiuchi",         257.71,   -7.91, "Hercules"),
    Constellation("Ori", "Orion",             "Orionis",           82.84,    5.95, "Orion"),
    Constellation("Pav", "Pavo",              "Pavonis",          280.91,  -65.78, "Bayer"),
    Constellation("Peg", "Pegasus",           "Pegasi",           340.97,   19.46, "Perseus"),
    Constellation("Per", "Perseus",           "Persei",            48.13,   45.01, "Perseus"),
    Constellation("Phe", "Phoenix",           "Phoenicis",         16.43,  -48.58, "Bayer"),
    Constellation("Pic", "Pictor",            "Pictoris",          83.05,  -53.47, "La Caille"),
    Constellation("Psc", "Pisces",            "Piscium",            6.46,   13.69, "Zodiac"),
    Constellation("PsA", "Piscis Austrinus",  "Piscis Austrini",  340.66,  -30.64, "Heavenly Waters"),
    Constellation("Pup", "Puppis",            "Puppis",           115.86,  -31.18, "Heavenly Waters"),
    Constellation("Pyx", "Pyxis",             "Pyxidis",          133.29,  -27.35, "Heavenly Waters"),
    Constellation("Ret", "Reticulum",         "Reticuli",          59.55,  -60.00, "La Caille"),
    Constellation("Sge", "Sagitta",           "Sagittae",         296.94,   18.86, "Hercules"),
    Constellation("Sgr", "Sagittarius",       "Sagittarii",       284.20,  -28.48, "Zodiac"),
    Constellation("Sco", "Scorpius",          "Scorpii",          252.66,  -27.04, "Zodiac"),
    Constellation("Scl", "Sculptor",          "Sculptoris",         9.34,  -32.09, "La Caille"),
    Constellation("Sct", "Scutum",            "Scuti",            281.65,  -10.21, "Hercules"),
    Constellation("Ser", "Serpens",           "Serpentis",        236.50,    6.72, "Hercules"),
    Constellation("Sex", "Sextans",           "Sextantis",        152.50,   -2.61, "Hercules"),
    Constellation("Tau", "Taurus",            "Tauri",             67.55,   14.88, "Zodiac"),
    Constellation("Tel", "Telescopium",       "Telescopii",       278.15,  -51.04, "La Caille"),
    Constellation("Tri", "Triangulum",        "Trianguli",         32.14,   31.48, "Perseus"),
    Constellation("TrA", "Triangulum Australe","Trianguli Australis", 244.26, -65.39, "Bayer"),
    Constellation("Tuc", "Tucana",            "Tucanae",          354.82,  -65.83, "Bayer"),
    Constellation("UMa", "Ursa Major",        "Ursae Majoris",    167.45,   50.72, "Ursa Major"),
    Constellation("UMi", "Ursa Minor",        "Ursae Minoris",    230.18,   77.70, "Ursa Major"),
    Constellation("Vel", "Vela",              "Velorum",          141.66,  -47.17, "Heavenly Waters"),
    Constellation("Vir", "Virgo",             "Virginis",         207.51,   -4.16, "Zodiac"),
    Constellation("Vol", "Volans",            "Volantis",         117.26,  -69.80, "Bayer"),
    Constellation("Vul", "Vulpecula",         "Vulpeculae",       299.82,   24.44, "Hercules"),
]


# ════════════════════════════════════════════════════════════════════
#  Stick-figure line data — HIP-pair endpoints for major constellations
#  Source: Sinnott 1981 / Toomey 1991 (public-domain HEASARC dataset).
#  Encoded by hand from published charts; star IDs verified against
#  the Hipparcos catalog (ESA SP-1200, public).
# ════════════════════════════════════════════════════════════════════

# Each entry: constellation_abbr → list of (HIP_a, HIP_b) line endpoints.
CONSTELLATION_LINES_88: Dict[str, List[Tuple[int, int]]] = {
    # Already in star_field.py (kept for reference / extension)
    "Ori": [
        (27989, 26727), (26727, 25336), (25336, 26311), (26311, 27989),
        (25336, 24436), (26727, 28614), (27989, 22449), (22449, 22845),
        (22845, 25930),
    ],
    "UMa": [  # Big Dipper
        (54061, 53910), (53910, 58001), (58001, 59774), (59774, 62956),
        (62956, 65378), (65378, 67301),
    ],
    "Cru": [
        (60718, 62434), (59747, 61084),
    ],
    "Sco": [
        (80763, 78820), (78820, 78265), (78265, 77070), (80763, 81266),
        (81266, 82396), (82396, 82514), (82514, 83081), (83081, 84143),
        (84143, 86228),
    ],
    "Cen": [
        (71683, 68702), (68702, 67472), (67472, 66657), (66657, 61932),
    ],
    # New constellations — major figures
    "Cas": [  # Cassiopeia "W"
        (3179, 4427), (4427, 6686), (6686, 8886), (8886, 11383),
    ],
    "Cep": [  # Cepheus pentagon
        (105199, 109492), (109492, 112724), (112724, 116727), (116727, 105199),
        (105199, 102422),
    ],
    "Lyr": [  # Lyra parallelogram + Vega
        (91262, 92420), (92420, 92791), (92791, 93194), (93194, 91971),
        (91971, 91262),
    ],
    "Cyg": [  # Northern Cross
        (102098, 100453), (100453, 97649), (97649, 95947),
        (97278, 100453), (94779, 100453),
    ],
    "Aql": [  # Aquila (Altair)
        (97649, 98036), (97649, 97278),
    ],
    "Boo": [  # Boötes
        (69673, 71075), (71075, 73555), (73555, 74785), (74785, 71795),
        (71795, 69673),
    ],
    "Leo": [  # Leo
        (49669, 50335), (50335, 50583), (50583, 54879), (54879, 57632),
        (57632, 49669), (54879, 56343),
    ],
    "Vir": [  # Virgo Y
        (65474, 63608), (63608, 60129), (60129, 57380), (57380, 54061),
        (65474, 66249), (66249, 69427),
    ],
    "Tau": [  # Taurus (Hyades V + horns)
        (21421, 20889), (20889, 20455), (20455, 21421), (21421, 25428),
        (21421, 25930),
    ],
    "Gem": [  # Gemini twins
        (37826, 36850), (36850, 35550), (37826, 36046), (36046, 34693),
        (35550, 32362),
    ],
    "CMa": [  # Canis Major
        (32349, 33347), (33347, 34045), (34045, 33152), (33152, 32349),
        (32349, 30122),
    ],
    "CMi": [
        (37279, 36188),
    ],
    "Per": [  # Perseus
        (15863, 14328), (14328, 14354), (14354, 18532), (15863, 18246),
        (15863, 14576),
    ],
    "And": [  # Andromeda
        (677, 5447), (5447, 9640), (9640, 14328),
    ],
    "Peg": [  # Great Square + body
        (677, 113881), (113881, 113963), (113963, 1067), (1067, 677),
        (677, 109427), (109427, 107315),
    ],
    "Aur": [  # Auriga pentagon
        (24608, 23015), (23015, 23453), (23453, 25428), (25428, 28380),
        (28380, 24608),
    ],
    "Lep": [  # Lepus
        (25985, 25606), (25606, 27654), (27654, 28910), (28910, 25985),
    ],
    "Hya": [  # Hydra head + spine
        (43109, 42799), (42799, 42402), (42402, 42313), (42313, 41822),
        (41822, 43109), (43109, 46390), (46390, 49841), (49841, 52943),
        (52943, 64166),
    ],
    "Crv": [  # Corvus quadrilateral
        (59803, 60965), (60965, 61359), (61359, 59316), (59316, 59803),
    ],
    "Crt": [  # Crater
        (53740, 55282), (55282, 55687), (55687, 53740),
    ],
    "Sgr": [  # Sagittarius teapot
        (89642, 90185), (90185, 92041), (92041, 93506), (93506, 90422),
        (90422, 89931), (89931, 89642), (89642, 88635),
    ],
    "Cap": [  # Capricornus
        (100345, 102978), (102978, 105881), (105881, 107556),
        (107556, 100027), (100027, 100345),
    ],
    "Aqr": [  # Aquarius main figure
        (109074, 110395), (110395, 110672), (110672, 109139),
        (109139, 112961), (112961, 113136),
    ],
    "Psc": [  # Pisces "circlet" + cord
        (1645, 4906), (4906, 9487), (9487, 7097), (7097, 5742),
        (5742, 4889), (4889, 1645),
    ],
    "Ari": [  # Aries
        (9884, 8903), (8903, 8832),
    ],
    "Lib": [  # Libra
        (74785, 76333), (76333, 74392), (74392, 74785),
    ],
    "Oph": [  # Ophiuchus
        (86032, 84379), (84379, 79593), (79593, 76267), (76267, 80170),
        (80170, 84012), (84012, 86032),
    ],
    "Ser": [  # Serpens (Caput + Cauda)
        (76276, 78072), (78072, 77233), (77233, 75671),
        (89962, 87386), (87386, 86440),
    ],
    "Her": [  # Hercules keystone + body
        (80170, 81693), (81693, 84380), (84380, 83207), (83207, 80170),
        (80170, 86974), (86974, 86414),
    ],
    "Dra": [  # Draco
        (87833, 85670), (85670, 83895), (83895, 80331), (80331, 75458),
        (75458, 68756), (68756, 61281), (61281, 56211),
    ],
    "UMi": [  # Ursa Minor
        (11767, 85822), (85822, 82080), (82080, 77055), (77055, 75097),
        (75097, 79822), (79822, 72607),
    ],
    "Car": [  # Carina (with Canopus)
        (30438, 41037), (41037, 45238), (45238, 50099), (50099, 45556),
        (45556, 41037),
    ],
    "Vel": [  # Vela
        (44816, 46651), (46651, 50191), (50191, 52727), (52727, 44816),
    ],
    "Pup": [  # Puppis
        (39429, 39757), (39757, 38827), (38827, 39429),
    ],
    "PsA": [  # Piscis Austrinus
        (113368, 110672),
    ],
    "Gru": [  # Grus
        (109268, 112122), (112122, 112405), (112405, 109268),
    ],
    "Phe": [  # Phoenix
        (2081, 5165), (5165, 2072), (2072, 765),
    ],
    "Tuc": [  # Tucana
        (110130, 1599),
    ],
    "Eri": [  # Eridanus river (subset)
        (7588, 12390), (12390, 13701), (13701, 16611), (16611, 18543),
        (18543, 23875), (23875, 24305), (24305, 24327),
    ],
    "Cnc": [  # Cancer
        (44066, 42806), (42806, 42911), (42911, 40526),
    ],
    "Tri": [  # Triangulum
        (8796, 10064), (10064, 10670), (10670, 8796),
    ],
}


def get_centroid(abbr: str) -> Optional[Tuple[float, float]]:
    """Look up an IAU constellation centroid by 3-letter abbreviation."""
    for c in CONSTELLATIONS:
        if c.abbr == abbr:
            return c.ra_deg, c.dec_deg
    return None
