"""Messier deep-sky catalog — all 110 objects from Charles Messier's
1771-1781 catalogue plus the M104-M110 additions by later editors.

Each entry has J2000 coordinates, integrated visual magnitude, angular
size (major × minor in arcminutes), and an object class. Coordinates
sourced from the SIMBAD database (CDS Strasbourg, public domain).

Object class codes:
  G  = galaxy
  GC = globular cluster
  OC = open cluster
  N  = diffuse / emission / reflection nebula
  PN = planetary nebula
  SR = supernova remnant
  AS = asterism / multiple star
  D  = double star

References:
    Messier, C. (1781) "Catalogue des nébuleuses & des amas d'étoiles"
        Connaissance des Temps, 1784.
    NGC/IC database, Wolfgang Steinicke, http://www.klima-luft.de/steinicke/
    SIMBAD CDS Strasbourg.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class MessierObject:
    """A single entry from the Messier catalog."""
    m: int               # Messier number (1-110)
    ngc: str             # NGC/IC designation (may be empty for IC)
    name: str            # Common name where applicable
    ra_deg: float        # J2000 RA
    dec_deg: float       # J2000 Dec
    vmag: float          # integrated apparent V magnitude
    size_amaj: float     # major axis [arcmin]
    size_amin: float     # minor axis [arcmin]
    obj_class: str       # G/GC/OC/N/PN/SR/AS/D


# 110 objects, J2000 from SIMBAD. Magnitudes & sizes from Steinicke (2024).
MESSIER: List[MessierObject] = [
    MessierObject(  1, "NGC 1952",  "Crab Nebula",                  83.6331,  22.0145,  8.4,   6.0,  4.0, "SR"),
    MessierObject(  2, "NGC 7089",  "",                            323.3625,  -0.8233,  6.5,  16.0, 16.0, "GC"),
    MessierObject(  3, "NGC 5272",  "",                            205.5483,  28.3772,  6.2,  18.0, 18.0, "GC"),
    MessierObject(  4, "NGC 6121",  "",                            245.8967, -26.5258,  5.6,  36.0, 36.0, "GC"),
    MessierObject(  5, "NGC 5904",  "",                            229.6383,   2.0808,  5.6,  23.0, 23.0, "GC"),
    MessierObject(  6, "NGC 6405",  "Butterfly Cluster",           265.0689, -32.2553,  4.2,  25.0, 25.0, "OC"),
    MessierObject(  7, "NGC 6475",  "Ptolemy Cluster",             268.4625, -34.7933,  3.3,  80.0, 80.0, "OC"),
    MessierObject(  8, "NGC 6523",  "Lagoon Nebula",               270.9042, -24.3867,  6.0,  90.0, 40.0, "N"),
    MessierObject(  9, "NGC 6333",  "",                            259.7992, -18.5161,  7.7,  12.0, 12.0, "GC"),
    MessierObject( 10, "NGC 6254",  "",                            254.2877,  -4.1003,  6.6,  20.0, 20.0, "GC"),
    MessierObject( 11, "NGC 6705",  "Wild Duck Cluster",           282.7667,  -6.2700,  6.3,  14.0, 14.0, "OC"),
    MessierObject( 12, "NGC 6218",  "",                            251.8092,  -1.9483,  6.7,  16.0, 16.0, "GC"),
    MessierObject( 13, "NGC 6205",  "Hercules Cluster",            250.4233,  36.4611,  5.8,  20.0, 20.0, "GC"),
    MessierObject( 14, "NGC 6402",  "",                            264.4006,  -3.2458,  7.6,  11.0, 11.0, "GC"),
    MessierObject( 15, "NGC 7078",  "",                            322.4933,  12.1675,  6.2,  18.0, 18.0, "GC"),
    MessierObject( 16, "NGC 6611",  "Eagle Nebula",                274.7000, -13.7878,  6.0,  35.0, 28.0, "N"),
    MessierObject( 17, "NGC 6618",  "Omega/Swan Nebula",           275.1958, -16.1717,  6.0,  46.0, 37.0, "N"),
    MessierObject( 18, "NGC 6613",  "",                            274.9958, -17.1006,  7.5,   9.0,  9.0, "OC"),
    MessierObject( 19, "NGC 6273",  "",                            255.6575, -26.2678,  6.8,  17.0, 17.0, "GC"),
    MessierObject( 20, "NGC 6514",  "Trifid Nebula",               270.6000, -23.0333,  6.3,  28.0, 28.0, "N"),
    MessierObject( 21, "NGC 6531",  "",                            271.0500, -22.5000,  5.9,  13.0, 13.0, "OC"),
    MessierObject( 22, "NGC 6656",  "Sagittarius Cluster",         279.0997, -23.9047,  5.1,  32.0, 32.0, "GC"),
    MessierObject( 23, "NGC 6494",  "",                            269.2667, -19.0167,  5.5,  27.0, 27.0, "OC"),
    MessierObject( 24, "IC 4715",   "Sagittarius Star Cloud",      274.2000, -18.5500,  4.6,  90.0, 90.0, "OC"),
    MessierObject( 25, "IC 4725",   "",                            277.9333, -19.2333,  4.6,  32.0, 32.0, "OC"),
    MessierObject( 26, "NGC 6694",  "",                            281.3208,  -9.3878,  8.0,  15.0, 15.0, "OC"),
    MessierObject( 27, "NGC 6853",  "Dumbbell Nebula",             299.9014,  22.7211,  7.4,   8.0,  6.0, "PN"),
    MessierObject( 28, "NGC 6626",  "",                            276.1369, -24.8697,  6.8,  11.2, 11.2, "GC"),
    MessierObject( 29, "NGC 6913",  "",                            305.9750,  38.5333,  6.6,   7.0,  7.0, "OC"),
    MessierObject( 30, "NGC 7099",  "",                            325.0925, -23.1797,  7.2,  11.0, 11.0, "GC"),
    MessierObject( 31, "NGC 224",   "Andromeda Galaxy",             10.6847,  41.2692,  3.4, 178.0, 63.0, "G"),
    MessierObject( 32, "NGC 221",   "",                             10.6742,  40.8653,  8.1,   8.7,  6.5, "G"),
    MessierObject( 33, "NGC 598",   "Triangulum Galaxy",            23.4621,  30.6602,  5.7,  73.0, 45.0, "G"),
    MessierObject( 34, "NGC 1039",  "",                             40.5167,  42.7833,  5.5,  35.0, 35.0, "OC"),
    MessierObject( 35, "NGC 2168",  "",                             92.2208,  24.3300,  5.3,  28.0, 28.0, "OC"),
    MessierObject( 36, "NGC 1960",  "",                             84.0792,  34.1372,  6.3,  12.0, 12.0, "OC"),
    MessierObject( 37, "NGC 2099",  "",                             88.0750,  32.5453,  6.2,  24.0, 24.0, "OC"),
    MessierObject( 38, "NGC 1912",  "",                             82.1750,  35.8333,  7.4,  21.0, 21.0, "OC"),
    MessierObject( 39, "NGC 7092",  "",                            322.8333,  48.4333,  5.5,  32.0, 32.0, "OC"),
    MessierObject( 40, "WNC 4",     "Winnecke 4 (double star)",    185.5500,  58.0833,  9.7,   0.8,  0.8, "D"),
    MessierObject( 41, "NGC 2287",  "",                            101.5042, -20.7567,  4.5,  38.0, 38.0, "OC"),
    MessierObject( 42, "NGC 1976",  "Orion Nebula",                 83.8222,  -5.3911,  4.0,  85.0, 60.0, "N"),
    MessierObject( 43, "NGC 1982",  "De Mairan's Nebula",           83.8800,  -5.2700,  9.0,  20.0, 15.0, "N"),
    MessierObject( 44, "NGC 2632",  "Beehive Cluster",             130.1000,  19.6667,  3.7,  95.0, 95.0, "OC"),
    MessierObject( 45, "—",         "Pleiades",                     56.7500,  24.1167,  1.6, 110.0, 110.0,"OC"),
    MessierObject( 46, "NGC 2437",  "",                            115.4458, -14.8194,  6.1,  27.0, 27.0, "OC"),
    MessierObject( 47, "NGC 2422",  "",                            114.1458, -14.4861,  4.4,  30.0, 30.0, "OC"),
    MessierObject( 48, "NGC 2548",  "",                            123.4167,  -5.7500,  5.8,  54.0, 54.0, "OC"),
    MessierObject( 49, "NGC 4472",  "",                            187.4444,   8.0042,  8.4,   9.0,  7.0, "G"),
    MessierObject( 50, "NGC 2323",  "",                            105.6667,  -8.3667,  5.9,  16.0, 16.0, "OC"),
    MessierObject( 51, "NGC 5194",  "Whirlpool Galaxy",            202.4696,  47.1953,  8.4,  11.2,  6.9, "G"),
    MessierObject( 52, "NGC 7654",  "",                            351.2000,  61.5917,  7.3,  13.0, 13.0, "OC"),
    MessierObject( 53, "NGC 5024",  "",                            198.2300,  18.1683,  7.6,  13.0, 13.0, "GC"),
    MessierObject( 54, "NGC 6715",  "",                            283.7637, -30.4797,  7.6,   9.1,  9.1, "GC"),
    MessierObject( 55, "NGC 6809",  "",                            294.9986, -30.9628,  6.3,  19.0, 19.0, "GC"),
    MessierObject( 56, "NGC 6779",  "",                            289.1486,  30.1836,  8.3,   7.1,  7.1, "GC"),
    MessierObject( 57, "NGC 6720",  "Ring Nebula",                 283.3962,  33.0292,  8.8,   1.4,  1.0, "PN"),
    MessierObject( 58, "NGC 4579",  "",                            189.4317,  11.8181,  9.7,   5.5,  4.5, "G"),
    MessierObject( 59, "NGC 4621",  "",                            190.5096,  11.6469,  9.6,   5.4,  3.7, "G"),
    MessierObject( 60, "NGC 4649",  "",                            190.9167,  11.5527,  8.8,   7.4,  6.0, "G"),
    MessierObject( 61, "NGC 4303",  "",                            185.4787,   4.4736,  9.7,   6.5,  5.9, "G"),
    MessierObject( 62, "NGC 6266",  "",                            255.3033,  -30.1136, 6.5,  15.0, 15.0, "GC"),
    MessierObject( 63, "NGC 5055",  "Sunflower Galaxy",            198.9554,  42.0293,  8.6,  12.6,  7.2, "G"),
    MessierObject( 64, "NGC 4826",  "Black Eye Galaxy",            194.1817,  21.6831,  8.5,  10.0,  5.4, "G"),
    MessierObject( 65, "NGC 3623",  "",                            169.7333,  13.0925,  9.3,   8.0,  1.5, "G"),
    MessierObject( 66, "NGC 3627",  "",                            170.0625,  12.9914,  8.9,   8.7,  4.4, "G"),
    MessierObject( 67, "NGC 2682",  "",                            132.8458,  11.8167,  6.9,  29.0, 29.0, "OC"),
    MessierObject( 68, "NGC 4590",  "",                            189.8667, -26.7444,  7.3,  11.0, 11.0, "GC"),
    MessierObject( 69, "NGC 6637",  "",                            277.8458, -32.3481,  7.6,   7.1,  7.1, "GC"),
    MessierObject( 70, "NGC 6681",  "",                            280.8033, -32.2922,  7.9,   7.8,  7.8, "GC"),
    MessierObject( 71, "NGC 6838",  "",                            298.4438,  18.7792,  8.2,   7.2,  7.2, "GC"),
    MessierObject( 72, "NGC 6981",  "",                            313.3650, -12.5378,  9.3,   5.9,  5.9, "GC"),
    MessierObject( 73, "NGC 6994",  "Asterism",                    314.7500, -12.6333,  9.0,   2.8,  2.8, "AS"),
    MessierObject( 74, "NGC 628",   "Phantom Galaxy",               24.1742,  15.7836,  9.4,  10.5,  9.5, "G"),
    MessierObject( 75, "NGC 6864",  "",                            301.5200, -21.9222,  8.5,   6.0,  6.0, "GC"),
    MessierObject( 76, "NGC 650",   "Little Dumbbell Nebula",       25.5817,  51.5750, 10.1,   2.7,  1.8, "PN"),
    MessierObject( 77, "NGC 1068",  "Cetus A",                      40.6696,  -0.0133,  8.9,   7.1,  6.0, "G"),
    MessierObject( 78, "NGC 2068",  "",                             86.6792,   0.0792,  8.3,   8.0,  6.0, "N"),
    MessierObject( 79, "NGC 1904",  "",                             81.0442, -24.5244,  8.0,   8.7,  8.7, "GC"),
    MessierObject( 80, "NGC 6093",  "",                            244.2600, -22.9750,  7.3,  10.0, 10.0, "GC"),
    MessierObject( 81, "NGC 3031",  "Bode's Galaxy",               148.8883,  69.0653,  6.9,  26.9,  14.1,"G"),
    MessierObject( 82, "NGC 3034",  "Cigar Galaxy",                148.9696,  69.6797,  8.4,  11.2,  4.3, "G"),
    MessierObject( 83, "NGC 5236",  "Southern Pinwheel",           204.2500, -29.8657,  7.5,  12.9, 11.5, "G"),
    MessierObject( 84, "NGC 4374",  "",                            186.2654,  12.8870,  9.1,   6.5,  5.6, "G"),
    MessierObject( 85, "NGC 4382",  "",                            186.3500,  18.1911,  9.1,   7.1,  5.5, "G"),
    MessierObject( 86, "NGC 4406",  "",                            186.5492,  12.9461,  8.9,   8.9,  5.8, "G"),
    MessierObject( 87, "NGC 4486",  "Virgo A",                     187.7058,  12.3911,  8.6,   8.3,  6.6, "G"),
    MessierObject( 88, "NGC 4501",  "",                            187.9967,  14.4197,  9.6,   6.9,  3.7, "G"),
    MessierObject( 89, "NGC 4552",  "",                            188.9158,  12.5563,  9.8,   5.1,  4.7, "G"),
    MessierObject( 90, "NGC 4569",  "",                            189.2071,  13.1628,  9.5,   9.5,  4.4, "G"),
    MessierObject( 91, "NGC 4548",  "",                            188.8600,  14.4961,  10.2,  5.4,  4.4, "G"),
    MessierObject( 92, "NGC 6341",  "",                            259.2808,  43.1356,  6.4,  14.0, 14.0, "GC"),
    MessierObject( 93, "NGC 2447",  "",                            116.1083, -23.8567,  6.2,  22.0, 22.0, "OC"),
    MessierObject( 94, "NGC 4736",  "",                            192.7212,  41.1203,  8.2,  11.2,  9.1, "G"),
    MessierObject( 95, "NGC 3351",  "",                            160.9904,  11.7039,  9.7,   7.4,  5.0, "G"),
    MessierObject( 96, "NGC 3368",  "",                            161.6904,  11.8197,  9.2,   7.6,  5.2, "G"),
    MessierObject( 97, "NGC 3587",  "Owl Nebula",                  168.6988,  55.0192,  9.9,   3.4,  3.3, "PN"),
    MessierObject( 98, "NGC 4192",  "",                            183.4517,  14.9000, 10.1,   9.8,  2.8, "G"),
    MessierObject( 99, "NGC 4254",  "",                            184.7067,  14.4163,  9.9,   5.4,  4.7, "G"),
    MessierObject(100, "NGC 4321",  "",                            185.7287,  15.8225,  9.3,   7.4,  6.3, "G"),
    MessierObject(101, "NGC 5457",  "Pinwheel Galaxy",             210.8021,  54.3489,  7.9,  28.8, 26.9, "G"),
    MessierObject(102, "NGC 5866",  "",                            226.6225,  55.7633,  9.9,   5.2,  2.3, "G"),
    MessierObject(103, "NGC 581",   "",                             23.3500,  60.6500,  7.4,   6.0,  6.0, "OC"),
    MessierObject(104, "NGC 4594",  "Sombrero Galaxy",             189.9976, -11.6231,  8.0,   8.7,  3.5, "G"),
    MessierObject(105, "NGC 3379",  "",                            161.9567,  12.5817,  9.3,   5.4,  4.8, "G"),
    MessierObject(106, "NGC 4258",  "",                            184.7400,  47.3037,  8.4,  18.6,  7.2, "G"),
    MessierObject(107, "NGC 6171",  "",                            248.1300, -13.0537,  7.8,  10.0, 10.0, "GC"),
    MessierObject(108, "NGC 3556",  "",                            167.8788,  55.6741, 10.0,   8.7,  2.2, "G"),
    MessierObject(109, "NGC 3992",  "",                            179.3996,  53.3747,  9.8,   7.6,  4.7, "G"),
    MessierObject(110, "NGC 205",   "",                             10.0917,  41.6850,  7.9,  21.9, 11.0, "G"),
]


def messier_by_class(obj_class: str) -> List[MessierObject]:
    """Return all Messier objects of the given class (G, GC, OC, N, PN, SR…)."""
    return [m for m in MESSIER if m.obj_class == obj_class]


def visible_messier(mag_limit: float = 9.0) -> List[MessierObject]:
    """Return Messier entries brighter than mag_limit, sorted bright→faint."""
    out = [m for m in MESSIER if m.vmag <= mag_limit]
    out.sort(key=lambda o: o.vmag)
    return out
