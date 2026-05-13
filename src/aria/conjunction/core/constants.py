"""
Physical constants for orbital mechanics.

Sources:
  - WGS-84 ellipsoid parameters
  - IAU 2010 best estimates
  - EGM-96 geopotential
"""

import math

# --- Gravitational Parameters ---
MU_EARTH = 3.986004418e14   # m³/s² — Earth gravitational parameter (WGS-84: NIMA TR8350.2, 3rd ed. 2000)
MU_EARTH_KM = 3.986004418e5 # km³/s² — same in km units (used with TLE-derived elements)
MU_SUN = 1.32712440018e20   # m³/s² — IAU 2010 best estimate (Pitjeva & Standish 2009 CeMDA 103 365)
MU_MOON = 4.9048695e12      # m³/s² — IAU 2010 best estimate (Folkner et al. 2014 IPN Prog Rpt 196)

# --- Earth Shape (WGS-84, NIMA TR8350.2) ---
R_EARTH_KM = 6378.137      # km — equatorial radius (WGS-84)
R_EARTH_M = 6378137.0      # m   — equatorial radius (WGS-84)
R_POLAR_KM = 6356.752      # km — polar radius (WGS-84)
FLATTENING = 1.0 / 298.257223563  # WGS-84 flattening (NIMA TR8350.2 §3.2)

# --- Earth Rotation ---
OMEGA_EARTH = 7.2921159e-5  # rad/s — sidereal rotation rate
SIDEREAL_DAY_S = 86164.0905  # seconds

# --- Geopotential Zonal Harmonics (EGM-96: Lemoine et al. 1998 NASA/TP-1998-206861) ---
J2 = 1.08262668355e-3   # oblateness — dominant perturbation (EGM-96)
J3 = -2.53265648533e-6  # pear-shape term (EGM-96)
J4 = -1.61098761735e-6  # (EGM-96)

# --- Derived Constants ---
TWO_PI = 2.0 * math.pi
DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi
MINUTES_PER_DAY = 1440.0
SECONDS_PER_DAY = 86400.0

# --- Default Screening Parameters (NASA CARA: Kelso 2009 AIAA 2009-6173) ---
DEFAULT_SCREENING_ALTITUDE_PAD_KM = 10.0   # km — ESTIMATE — apogee/perigee filter padding
DEFAULT_MOID_THRESHOLD_KM = 20.0           # km — NASA CARA 20 km screening threshold (Kelso 2009)
DEFAULT_SCREENING_WINDOW_HOURS = 72        # hours — NASA CARA 3-day window (Kelso 2009)
DEFAULT_TIME_STEP_S = 60.0                 # seconds — ESTIMATE — 60 s coarse TCA search step

# --- Collision Probability Thresholds (NASA CARA: Foster & Estes 1992 §3) ---
PC_RED_THRESHOLD = 1e-4   # maneuver required (NASA CARA red threshold)
PC_YELLOW_THRESHOLD = 1e-5 # monitor closely (NASA CARA yellow threshold)
MAHALANOBIS_SKIP_THRESHOLD = 5.0  # ESTIMATE — skip Pc if D_M > 5 (Alfano 2005 JGCD 28 427)

# --- Default Object Sizes (meters, radius; DISCOS catalog: Klinkrad 2006 §3.2) ---
DEFAULT_PAYLOAD_RADIUS_M = 2.0        # ESTIMATE — ~2 m radius typical LEO payload (Klinkrad 2006)
DEFAULT_DEBRIS_RADIUS_M = 0.1         # ESTIMATE — 0.1 m debris fragment (Klinkrad 2006 §3.2)
DEFAULT_ROCKET_BODY_RADIUS_M = 3.0    # ESTIMATE — 3 m radius rocket body (Klinkrad 2006)
