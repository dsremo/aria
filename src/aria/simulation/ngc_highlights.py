"""Non-Messier deep-sky highlights — NGC, IC, and well-known asterisms.

Charles Messier's catalog stopped at 110 objects, leaving out most of the
southern sky and many beautiful northern objects that don't appear in
his comet-hunter's list. This module covers the gaps:

- **LMC / SMC** — Magellanic Clouds, naked-eye southern dwarf galaxies
- **NGC 104 (47 Tucanae)** — second-brightest globular cluster
- **Double Cluster (NGC 869 + 884)** — naked-eye in Perseus
- **Helix Nebula (NGC 7293)** — largest planetary nebula
- **Veil Nebula complex** (NGC 6960/6992/6995)
- **Rosette Nebula (NGC 2237)**
- **Ring Nebula south variants** (NGC 3132 "Eight-burst")
- **NGC 253** — Sculptor starburst galaxy
- **Running Chicken Nebula (IC 2944)**
...and more.

Public-domain astronomical data from the NGC 2000.0 database (Sinnott
1988) and SIMBAD. No copyrightable expression.

Reference:
    Sinnott, R. W. (1988) "NGC 2000.0: The Complete New General Catalogue
        and Index Catalogues of Nebulae and Star Clusters by J. L. E.
        Dreyer." Sky Publishing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class NGCObject:
    catalog_id: str       # "NGC 253" / "IC 2944" / "Collinder 33" / "Melotte 20"
    common_name: str
    ra_deg: float
    dec_deg: float
    vmag: float
    size_amin: float
    obj_class: str        # 'G' / 'GC' / 'OC' / 'N' / 'PN' / 'SR' / 'dwarf_G' / 'asterism'
    description: str


NGC_HIGHLIGHTS: List[NGCObject] = [
    # Galaxies
    NGCObject("LMC",          "Large Magellanic Cloud",     80.8938, -69.7561,  0.9, 650,  "dwarf_G",
              "Satellite galaxy of the Milky Way, ~163,000 ly; Tarantula Nebula within"),
    NGCObject("SMC",          "Small Magellanic Cloud",     13.1867, -72.8286,  2.2, 320,  "dwarf_G",
              "Second-nearest satellite, ~200,000 ly; hosts NGC 104 & NGC 362 globulars"),
    NGCObject("NGC 253",      "Sculptor Galaxy",             11.8879, -25.2883,  8.0,  28,  "G",
              "Nearby starburst spiral, edge-on; dusty arms visible in telescopes"),
    NGCObject("NGC 891",      "Silver Sliver Galaxy",        35.6394, +42.3493, 10.0,  13,  "G",
              "Classic edge-on spiral with prominent dust lane"),
    NGCObject("NGC 1365",     "Great Barred Spiral",         53.4019, -36.1403,  9.5,  11,  "G",
              "Massive barred spiral in Fornax Cluster"),
    NGCObject("NGC 2403",     "—",                          114.2143, +65.6028,  8.9,  21,  "G",
              "Nearby spiral near M81/M82, bridge to the M81 Group"),
    NGCObject("NGC 5128",     "Centaurus A",                201.3651, -43.0191,  6.8,  25,  "G",
              "Peculiar radio galaxy with prominent dust lane"),
    NGCObject("NGC 4565",     "Needle Galaxy",              189.0866, +25.9876,  9.6,  16,  "G",
              "Edge-on spiral in Coma Berenices"),
    NGCObject("NGC 6822",     "Barnard's Galaxy",           296.2380, -14.8036,  8.8,  15,  "G",
              "Local Group dwarf irregular ~1.6 Mly away"),

    # Globular clusters (beyond M)
    NGCObject("NGC 104",      "47 Tucanae",                   6.0237, -72.0812,  4.0,  50,  "GC",
              "Second-brightest globular cluster after Omega Cen (naked eye in SMC region)"),
    NGCObject("NGC 5139",     "Omega Centauri",             201.6970, -47.4795,  3.7,  55,  "GC",
              "Largest globular cluster in the Milky Way; millions of stars"),
    NGCObject("NGC 6397",     "—",                          265.1751, -53.6744,  5.7,  26,  "GC",
              "Nearest globular cluster (~7,800 ly)"),
    NGCObject("NGC 6752",     "—",                          287.7171, -59.9855,  5.4,  29,  "GC",
              "Third-brightest globular; fine cluster in Pavo"),

    # Open clusters
    NGCObject("NGC 869",      "Double Cluster (h Per)",      35.5050, +57.1361,  5.3,  30,  "OC",
              "Naked-eye pair with NGC 884; Perseus Chi-h cluster"),
    NGCObject("NGC 884",      "Double Cluster (χ Per)",      35.9642, +57.1478,  6.1,  30,  "OC",
              "Companion of NGC 869; dense young open cluster"),
    NGCObject("IC 2602",      "Southern Pleiades",          160.7167, -64.4017,  1.9,  50,  "OC",
              "Naked-eye open cluster around theta Carinae"),
    NGCObject("IC 2391",      "Omicron Velorum Cluster",    130.0417, -52.9333,  2.5,  50,  "OC",
              "Bright naked-eye cluster in Vela"),
    NGCObject("Melotte 20",   "Alpha Persei Cluster",        51.0812, +49.8617,  2.3, 185,  "OC",
              "Huge moving group around Mirfak"),
    NGCObject("Collinder 285","Ursa Major Moving Group",    200.0000, +55.0000,  2.0, 400,  "asterism",
              "Kinematic group anchored by the Big Dipper's stars"),
    NGCObject("NGC 2244",     "Rosette Cluster",             97.9844,  +4.9322,  4.8,  24,  "OC",
              "Hot young cluster ionizing the Rosette Nebula"),
    NGCObject("NGC 2264",     "Christmas Tree Cluster",     100.2417,  +9.8844,  3.9,  40,  "OC",
              "Triangular open cluster + Cone Nebula"),
    NGCObject("NGC 6231",     "—",                          253.5417, -41.8280,  2.6,  14,  "OC",
              "Bright young cluster in Scorpius (\"Northern Jewel Box\")"),
    NGCObject("NGC 4755",     "Jewel Box",                  193.3583, -60.3500,  4.2,  10,  "OC",
              "Sparkling open cluster just next to β Crucis"),

    # Nebulae — emission / reflection / planetary
    NGCObject("NGC 7000",     "North America Nebula",       314.7500, +44.3667,  4.0, 120,  "N",
              "Continent-shaped emission nebula near Deneb"),
    NGCObject("NGC 6960",     "Western Veil Nebula",        312.4000, +30.7000,  7.0,  70,  "SR",
              "Part of the Cygnus Loop supernova remnant"),
    NGCObject("NGC 6992",     "Eastern Veil Nebula",        313.0000, +31.7000,  7.0,  60,  "SR",
              "Other half of the Veil SNR — both excellent in OIII filter"),
    NGCObject("NGC 2237",     "Rosette Nebula",              97.9833,  +4.9333,  9.0,  80,  "N",
              "Large emission nebula with NGC 2244 cluster at center"),
    NGCObject("IC 434",       "Horsehead Nebula",            85.2875,  -2.4583,  7.3,   4,  "N",
              "Silhouette dark nebula in Orion's Belt"),
    NGCObject("NGC 2024",     "Flame Nebula",                85.4417,  -1.8500,  2.0,  30,  "N",
              "Emission nebula near Alnitak in Orion"),
    NGCObject("IC 1396",      "Elephant's Trunk",           324.7375, +57.4917,  3.5, 170,  "N",
              "Large H II region with pillars of dust"),
    NGCObject("IC 2944",      "Running Chicken Nebula",     167.7583, -63.3000,  4.5,  75,  "N",
              "Southern emission complex with Thackeray's Globules"),
    NGCObject("NGC 7293",     "Helix Nebula",               337.4100, -20.8367,  7.6,  28,  "PN",
              "Closest bright planetary nebula (~655 ly), 'Eye of God'"),
    NGCObject("NGC 3242",     "Ghost of Jupiter",           156.6800, -18.6303,  8.6,   1,  "PN",
              "Bright planetary nebula in Hydra"),
    NGCObject("NGC 3132",     "Eight-Burst Nebula",         151.7608, -40.4372,  9.2,   1,  "PN",
              "Elliptical planetary nebula with layered shells"),
    NGCObject("NGC 6302",     "Bug Nebula",                 258.4333, -37.1094,  9.6,   1,  "PN",
              "Bipolar planetary nebula with hot central star"),
    NGCObject("NGC 40",       "Bow-Tie Nebula",               3.3225, +72.5211, 11.4,   1,  "PN",
              "Small round PN in Cepheus"),

    # Supernova remnants
    NGCObject("Cas A",        "Cassiopeia A",               350.8500, +58.8133,  0.0,   5,  "SR",
              "Youngest known galactic SNR (~350 yr), strong radio source"),
    NGCObject("Vela SNR",     "Gum Nebula complex",         128.5000, -45.5000,  2.0, 600,  "SR",
              "Vast shell remnant, pulsar near center"),
]
