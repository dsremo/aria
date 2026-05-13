"""Famous visual double / multiple stars.

Binoculars and small-telescope targets: pairs with enough angular
separation to split at the eyepiece, plus historical classics like Mizar
& Alcor (the naked-eye test) and Albireo (Cygnus gold + blue contrast).

Fields per entry:
  name        primary-star common name (or system designation)
  ra/dec      J2000 coords of primary
  mag_a/mag_b V magnitudes of the two brightest components
  sep_arcsec  angular separation of A-B
  pa_deg      position angle of B from A (N through E)
  spec_a/b    spectral types (from SIMBAD / GCVS)
  notes       popular description

Data: Washington Double Star Catalog (WDS) / Aitken (ADS), AAVSO — all
public-domain astronomical observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class DoubleStar:
    name: str
    hip_id: int
    ra_deg: float
    dec_deg: float
    mag_a: float
    mag_b: float
    sep_arcsec: float
    pa_deg: int
    spec_a: str
    spec_b: str
    notes: str


DOUBLES: List[DoubleStar] = [
    DoubleStar("Albireo (β Cyg)",            95947, 292.6800,  27.9600, 3.1, 5.1,   34.3, 54,
               "K2II", "B8V",  "Gold-blue color contrast — the archetypal telescope double"),
    DoubleStar("Mizar + Alcor",              65378, 200.9814,  54.9254, 2.2, 4.0,  708.7, 71,
               "A1V",  "A5V",  "Naked-eye test pair in Ursa Major (the horse and rider)"),
    DoubleStar("Almach (γ And)",              9640,  30.9748,  42.3300, 2.3, 5.0,    9.6, 63,
               "K3II", "B8V",  "Orange + blue-green pair; rivals Albireo"),
    DoubleStar("Castor (α Gem)",             36850, 113.6497,  31.8883, 1.9, 2.9,    5.1, 59,
               "A1V",  "A2V",  "Binary of A-type stars; actually a sextuple system"),
    DoubleStar("Cor Caroli (α CVn)",         63125, 194.0068,  38.3184, 2.9, 5.6,   19.3, 229,
               "A0p",  "F0V",  "Bright naked-eye pair in Canes Venatici"),
    DoubleStar("Rasalgethi (α Her)",         84345, 258.6618,  14.3903, 3.5, 5.4,    4.6, 106,
               "M5III", "G5III", "Orange-green-blue triple (visual double)"),
    DoubleStar("Ras Algethi C",                  0, 258.6607,  14.3904, 5.4, 5.4,    4.0, 100,
               "G5III", "F2V",  "Secondary of α Her; itself a close binary"),
    DoubleStar("ν Draconis",                 85819, 263.1542,  55.1846, 4.9, 4.9,   62.0, 311,
               "A9V",  "A8Vm", "Easy 'twin' double in Draco's head"),
    DoubleStar("Porrima (γ Vir)",            61941, 190.4150,  -1.4494, 3.5, 3.5,    3.0, 9,
               "F0V",  "F0V",  "Binary with 169-yr orbit; closest separation 2005"),
    DoubleStar("Izar (ε Boo)",               72105, 221.2466,  27.0742, 2.5, 4.6,    2.9, 344,
               "K0II", "A2V",  "Blue-orange 'pulcherrima'"),
    DoubleStar("Polaris (α UMi)",            11767,  37.9543,  89.2641, 2.0, 9.0,   18.4, 217,
               "F7Ib", "F3V",  "Pole Star + faint companion"),
    DoubleStar("β Mon",                      30867,  97.2041,  -7.0333, 4.7, 5.2,    7.1, 132,
               "B3Ve", "B3Ve", "Triple system — three similar-brightness B stars"),
    DoubleStar("Sigma Orionis",              26549,  84.6866,  -2.6000, 3.7, 6.6,   11.1, 238,
               "O9V",  "B0V",  "Multiple system at Orion's belt, trapezium-like"),
    DoubleStar("Trapezium (θ¹ Ori)",         26220,  83.8182,  -5.3880, 5.1, 6.7,    8.8, 270,
               "O7V",  "B0V",  "Core of the Orion Nebula; four bright OB stars"),
    DoubleStar("95 Herculis",                87212, 267.3600,  21.4372, 4.9, 5.2,    6.3, 258,
               "A5III","G5III", "Silver + gold color contrast"),
    DoubleStar("Kuma (ν Dra)",               85819, 263.0542,  55.1847, 4.9, 4.9,   62.0, 311,
               "A9V",  "A8V",  "Binoculars show both equally bright"),
    DoubleStar("Epsilon Lyrae (Double Double)", 91919, 281.0833, 39.6134, 4.7, 4.5,  208.0, 173,
               "A3V",  "A6Vn", "Each of the 'double' is itself binary — quadruple"),
    DoubleStar("ξ Bootis",                   72659, 222.8620,  19.1003, 4.7, 6.8,    5.5, 289,
               "G8V",  "K4V",  "Nearby (22 ly) binary with 152-yr orbit"),
    DoubleStar("70 Ophiuchi",                88601, 271.3783,   2.5005, 4.2, 6.0,    6.2, 131,
               "K0V",  "K5V",  "Nearby K-dwarf binary (17 ly)"),
    DoubleStar("Struve 2816 (in IC 1396)",        0, 324.4167,  57.4917, 5.7, 7.7,   11.8, 338,
               "O6V",  "O8V",  "Triple in the Elephant's Trunk region"),
]
