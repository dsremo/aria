"""Famous pulsars — rotation periods, discovery context, historical importance.

Pulsars are rapidly-rotating magnetized neutron stars, detected as
highly-regular radio/X-ray/gamma pulses. The 1967 discovery of PSR B1919+21
(Jocelyn Bell Burnell) opened a new astronomical window. This module lists
notable pulsars with enough parameters to compute current rotation phase
given the reference epoch.

Values are from the ATNF Pulsar Catalogue (CSIRO, Manchester et al. 2005)
and ApJ discovery papers — all public-domain astronomical observation.

Reference:
    Manchester, R. N., Hobbs, G. B., Teoh, A., Hobbs, M. (2005)
        "The Australia Telescope National Facility Pulsar Catalogue,"
        AJ 129:1993.  https://www.atnf.csiro.au/research/pulsar/psrcat/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Pulsar:
    jname: str               # J2000 designation (e.g. "J0534+2200")
    bname: str               # B1950 designation (e.g. "B0531+21")
    common_name: str
    ra_deg: float            # J2000
    dec_deg: float
    period_ms: float         # rotation period (ms)
    period_dot: float        # Ṗ (s/s, dimensionless spin-down rate)
    distance_kpc: float      # approx. distance (kpc; 1 kpc = 3262 ly)
    description: str


PULSARS: List[Pulsar] = [
    Pulsar("J0534+2200", "B0531+21", "Crab Pulsar (M1)",
           83.6333, 22.0144, 33.6, 4.2e-13, 2.00,
           "Center of Crab Nebula; SN 1054 remnant; first optical pulsar"),
    Pulsar("J1919+21",   "B1919+21",  "LGM-1 (first pulsar discovered)",
           290.0000, 21.8933, 1337.3, 1.35e-15, 0.30,
           "Jocelyn Bell Burnell 1967 — nicknamed 'Little Green Men 1'"),
    Pulsar("J0835-4510", "B0833-45", "Vela Pulsar",
           128.8350, -45.1764, 89.4, 1.25e-13, 0.29,
           "Remnant of Vela SNR; brightest gamma-ray pulsar"),
    Pulsar("J0437-4715", "—",        "Nearest millisecond pulsar",
            69.3158, -47.2522, 5.76, 5.73e-20, 0.14,
            "Closest known radio pulsar (~510 ly); binary with white dwarf"),
    Pulsar("J0953+0755", "B0950+08",  "—",
           148.2889,  7.9269,  253.1, 2.3e-16, 0.26,
           "One of the brightest radio pulsars"),
    Pulsar("J1939+2134","B1937+21",   "First millisecond pulsar",
           294.9108, 21.5833,   1.558, 1.05e-19, 3.60,
           "Discovered 1982; fastest known at the time (Backer 1982)"),
    Pulsar("J1748-2446ad","—",        "Terzan 5 ad (fastest)",
           266.9750, -24.7800,   1.395, 0.0, 5.50,
           "Fastest-known rotating pulsar — 716 Hz (Hessels 2006)"),
    Pulsar("J0633+1746","B0633+17",   "Geminga",
           98.4763, 17.7700,  237.1, 1.10e-14, 0.25,
           "Second-closest known pulsar; no radio emission (Bignami 1987)"),
    Pulsar("J1614-2230","—",          "Heavy neutron star",
           243.6500,-22.5083,    3.15, 9.60e-21, 0.70,
           "2M⊙ neutron star; ruled out soft EOS models (Demorest 2010)"),
    Pulsar("J0737-3039A","—",         "Double pulsar primary",
           114.4637,-30.6600,   22.70, 1.76e-18, 0.60,
           "Only known double pulsar system; GR test lab (Burgay 2003)"),
    Pulsar("J1745-2900","—",          "Magnetar near Sgr A*",
           266.4181,-29.0033, 3764.0, 6.61e-12, 8.30,
           "Closest known magnetar to Galactic Center supermassive BH"),
    Pulsar("J0108-1431","—",          "Faint nearby pulsar",
            17.1125,-14.5188,  807.6, 7.7e-17, 0.21,
            "Very faint 0.21 kpc pulsar — useful for propagation studies"),
    Pulsar("J1856-3754","—",          "Isolated neutron star",
           284.1467,-37.9075, 7056.0, 2.97e-14, 0.12,
           "Nearest isolated neutron star (~390 ly); visible in X-ray"),
    Pulsar("J1856+0113","B1853+01",   "—",
           284.1473,  1.2211,  267.4, 2.08e-13, 3.30,
           "Pulsar-wind nebula in W44 supernova remnant"),
    Pulsar("J1302-6350","B1259-63",   "Binary with Be star",
           195.6988,-63.8361, 47.8, 2.27e-15, 2.30,
           "Pulsar in 3.4-year eccentric orbit around massive Be star"),
]
