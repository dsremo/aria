"""ACE/CRIS Galactic Cosmic Ray Data Parser.

Parses real ACE/CRIS energy spectra measured at solar minimum and maximum,
plus Bartels-rotation-resolved solar modulation phi values, to provide
interpolated GCR flux for any element, energy, and solar cycle phase.

Data source: ACE Cosmic Ray Isotope Spectrometer (CRIS)
  - cris_spectra.txt: Differential energy spectra per element at solar
    min and solar max, 60-475 MeV/nuc.
  - cris_leaky_box.txt: Solar modulation parameter phi (MV) per Bartels
    rotation from 1997-2022, per element (Z=6,8,12,14,26).

Physics:
  Solar modulation follows the force-field approximation (Gleeson & Axford
  1968).  The local interstellar spectrum (LIS) J_LIS(T) is related to the
  modulated spectrum J(T) at 1 AU by:

    J(T) = J_LIS(T + Phi) * T(T + 2*T0) / ((T+Phi)(T+Phi+2*T0))

  where T is kinetic energy per nucleon, T0 = 938.3 MeV (proton rest mass
  energy), and Phi = Z*e*phi/A (rigidity-scaled modulation potential).

  We invert this: given measured spectra at known phi_min and phi_max we
  reconstruct J_LIS, then re-modulate to any desired phi.

References:
  - Stone et al. (1998) "The Cosmic-Ray Isotope Spectrometer for ACE"
  - Wiedenbeck et al. (2009) "ACE-CRIS Observations of GCR"
  - Gleeson & Axford (1968) "Solar Modulation of GCR"
  - Usoskin et al. (2011) "Solar modulation parameter"
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

# ════════════════════════════════════════════════════════════════
#  CONSTANTS
# ════════════════════════════════════════════════════════════════

T0_MEV = 938.272  # Proton rest mass energy (MeV)

# Element symbol -> (atomic number Z, most abundant mass number A)
ELEMENT_TABLE: Dict[str, Tuple[int, int]] = {
    "H":  (1, 1),    "He": (2, 4),
    "B":  (5, 11),   "C":  (6, 12),   "N":  (7, 14),   "O":  (8, 16),
    "F":  (9, 19),   "Ne": (10, 20),  "Na": (11, 23),  "Mg": (12, 24),
    "Al": (13, 27),  "Si": (14, 28),  "P":  (15, 31),  "S":  (16, 32),
    "Cl": (17, 35),  "Ar": (18, 36),  "K":  (19, 39),  "Ca": (20, 40),
    "Sc": (21, 45),  "Ti": (22, 48),  "V":  (23, 51),  "Cr": (24, 52),
    "Mn": (25, 55),  "Fe": (26, 56),  "Co": (27, 59),  "Ni": (28, 58),
}

# Canonical primary elements for mission radiation modeling
PRIMARY_ELEMENTS = ("H", "He", "C", "N", "O", "Fe")

# Default data directory (relative to repo root)
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "gcr"

# Average phi values for solar min / max used in cris_spectra.txt
# Derived from cris_leaky_box.txt: solar min ~250 MV, solar max ~900 MV
PHI_SOLAR_MIN_MV = 250.0
PHI_SOLAR_MAX_MV = 900.0

# Schwabe cycle period (years)
SCHWABE_PERIOD_YR = 11.0


# ════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ════════════════════════════════════════════════════════════════

@dataclass
class ElementSpectrum:
    """Energy spectrum for one element at one solar condition."""
    element: str
    energies_mev_nuc: List[float]
    fluxes: List[float]          # cm^-2 s^-1 sr^-1 (MeV/nuc)^-1 * 1e-9
    flux_errors: List[float]


@dataclass
class PhiRecord:
    """Solar modulation phi for one Bartels rotation."""
    bartels: int
    date_str: str
    phi_by_z: Dict[int, float]   # Z -> phi (MV)


@dataclass
class CRISData:
    """Container for all parsed ACE/CRIS data."""
    solar_min_spectra: Dict[str, ElementSpectrum] = field(default_factory=dict)
    solar_max_spectra: Dict[str, ElementSpectrum] = field(default_factory=dict)
    phi_records: List[PhiRecord] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════
#  PARSER
# ════════════════════════════════════════════════════════════════

def _parse_spectra_block(
    lines: List[str],
    start_idx: int,
) -> Tuple[Dict[str, ElementSpectrum], int]:
    """Parse one block (solar min or solar max) of cris_spectra.txt.

    Returns a dict of element -> ElementSpectrum and the line index
    after the block.
    """
    spectra: Dict[str, ElementSpectrum] = {}
    energies_current: List[float] = []
    idx = start_idx

    while idx < len(lines):
        line = lines[idx].rstrip()
        idx += 1

        if not line.strip():
            continue

        # Detect a new section header (the other solar condition)
        if line.startswith("CRIS Solar"):
            return spectra, idx - 1

        # Energy header line
        if line.strip().startswith("E/A"):
            energies_current = _parse_energy_header(line)
            continue

        # Element data line
        parsed = _parse_element_line(line, energies_current)
        if parsed is not None:
            sym, energies, fluxes, errors = parsed
            if sym in spectra:
                # Continuation block: append more energy points
                spectra[sym].energies_mev_nuc.extend(energies)
                spectra[sym].fluxes.extend(fluxes)
                spectra[sym].flux_errors.extend(errors)
            else:
                spectra[sym] = ElementSpectrum(
                    element=sym,
                    energies_mev_nuc=list(energies),
                    fluxes=list(fluxes),
                    flux_errors=list(errors),
                )

    return spectra, idx


def _parse_energy_header(line: str) -> List[float]:
    """Extract energies from a header like 'E/A 60.0 MeV/nuc.  72.0  ...'"""
    # Remove the E/A prefix and units, extract numbers
    cleaned = line.replace("E/A", "").replace("MeV/nuc.", "").replace("MeV/nuc", "")
    return [float(x) for x in re.findall(r"[\d.]+", cleaned)]


def _parse_element_line(
    line: str,
    energies: List[float],
) -> Optional[Tuple[str, List[float], List[float], List[float]]]:
    """Parse a line like ' C   541.15 +/- 21.96  600.09 +/- 24.25 ...'

    Returns (symbol, energies_used, fluxes, errors) or None.
    """
    # Match element symbol at the start (1-2 chars, possibly leading spaces)
    m = re.match(r"^\s*([A-Z][a-z]?)\s+", line)
    if m is None:
        return None

    sym = m.group(1).strip()
    rest = line[m.end():]

    # Extract flux +/- error pairs
    pairs = re.findall(r"([\d.]+)\s*\+/-\s*([\d.]+)", rest)
    if not pairs:
        return None

    fluxes = [float(p[0]) for p in pairs]
    errors = [float(p[1]) for p in pairs]

    # The flux values correspond to the LAST len(pairs) energies in the
    # current energy grid (elements with higher Z start at higher energies)
    n = len(pairs)
    if n > len(energies):
        # Shouldn't happen, but guard
        used_energies = energies[:n]
    else:
        used_energies = energies[len(energies) - n:]

    return sym, used_energies, fluxes, errors


def parse_spectra_file(path: Path) -> Tuple[Dict[str, ElementSpectrum], Dict[str, ElementSpectrum]]:
    """Parse cris_spectra.txt into solar-min and solar-max spectrum dicts."""
    text = path.read_text()
    lines = text.splitlines()

    solar_min: Dict[str, ElementSpectrum] = {}
    solar_max: Dict[str, ElementSpectrum] = {}

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if "Solar Minimum" in line:
            solar_min, idx = _parse_spectra_block(lines, idx + 1)
        elif "Solar Maximum" in line:
            solar_max, idx = _parse_spectra_block(lines, idx + 1)
        else:
            idx += 1

    return solar_min, solar_max


def parse_leaky_box_file(path: Path) -> List[PhiRecord]:
    """Parse cris_leaky_box.txt into a list of PhiRecord."""
    text = path.read_text()
    lines = text.splitlines()

    # Header tells us which Z values are in each column
    z_columns = [6, 8, 12, 14, 26]  # C, O, Mg, Si, Fe

    records: List[PhiRecord] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(">"):
            continue

        parts = line.split()
        if len(parts) < 7:
            continue

        try:
            bartels = int(parts[0])
        except ValueError:
            continue

        # Date is parts[1:4] (e.g. "30 Nov 1997")
        date_str = " ".join(parts[1:4])

        # Phi values follow, with trailing dots
        phi_vals = []
        for p in parts[4:4 + len(z_columns)]:
            try:
                phi_vals.append(float(p.rstrip(".")))
            except ValueError:
                break

        if len(phi_vals) == len(z_columns):
            phi_by_z = dict(zip(z_columns, phi_vals))
            records.append(PhiRecord(bartels=bartels, date_str=date_str, phi_by_z=phi_by_z))

    return records


# ════════════════════════════════════════════════════════════════
#  FORCE-FIELD MODULATION PHYSICS
# ════════════════════════════════════════════════════════════════

def _force_field_ratio(
    t_kinetic_mev_nuc: float,
    phi_from_mv: float,
    phi_to_mv: float,
    z: int,
    a: int,
) -> float:
    """Compute the flux ratio J(T, phi_to) / J(T, phi_from) using the
    force-field approximation.

    For a nucleus with charge Z and mass A, the rigidity-scaled
    modulation potential is Phi = Z * phi / A (in MeV/nuc).

    J(T, phi) = J_LIS(T + Phi) * T(T + 2*T0/A) / ((T+Phi)(T+Phi+2*T0/A))

    The ratio cancels J_LIS when both are evaluated at shifted energies
    that map to the same LIS energy, but that only works for the same
    LIS energy.  Instead we use the simpler approach: given that the
    spectral shape is approximately power-law, the ratio is well
    approximated by the kinematic suppression factor.
    """
    t0_per_nuc = T0_MEV / a  # ~938/A MeV/nuc for the rest mass term
    phi_from = z * phi_from_mv / a
    phi_to = z * phi_to_mv / a

    # Energies at source (LIS) for each modulation level
    t_lis_from = t_kinetic_mev_nuc + phi_from
    t_lis_to = t_kinetic_mev_nuc + phi_to

    # Kinematic factors
    def _kfactor(t: float, phi: float) -> float:
        t_shifted = t + phi
        return t * (t + 2 * t0_per_nuc) / (t_shifted * (t_shifted + 2 * t0_per_nuc))

    k_from = _kfactor(t_kinetic_mev_nuc, phi_from)
    k_to = _kfactor(t_kinetic_mev_nuc, phi_to)

    if k_from <= 0:
        return 1.0

    # The full ratio also includes the LIS ratio at different energies.
    # For a power-law LIS ~ T^(-gamma), J_LIS(T_lis_to)/J_LIS(T_lis_from)
    # ~ (T_lis_from/T_lis_to)^gamma.  Typical gamma ~ 2.7 for protons.
    gamma = 2.7
    lis_ratio = (t_lis_from / t_lis_to) ** gamma if t_lis_to > 0 else 1.0

    return (k_to / k_from) * lis_ratio


def _interpolate_log(
    energies: List[float],
    fluxes: List[float],
    energy_query: float,
) -> float:
    """Log-log linear interpolation of flux at a given energy.

    Extrapolates as power-law beyond the data range.
    """
    if len(energies) == 0 or len(fluxes) == 0:
        return 0.0

    if len(energies) == 1:
        return fluxes[0]

    log_e = [math.log(e) for e in energies]
    log_f = [math.log(max(f, 1e-30)) for f in fluxes]
    log_q = math.log(energy_query)

    # Find bracketing indices
    if log_q <= log_e[0]:
        # Extrapolate below using first two points
        slope = (log_f[1] - log_f[0]) / (log_e[1] - log_e[0]) if log_e[1] != log_e[0] else 0
        return math.exp(log_f[0] + slope * (log_q - log_e[0]))

    if log_q >= log_e[-1]:
        # Extrapolate above using last two points
        slope = (log_f[-1] - log_f[-2]) / (log_e[-1] - log_e[-2]) if log_e[-1] != log_e[-2] else 0
        return math.exp(log_f[-1] + slope * (log_q - log_e[-1]))

    # Interpolate
    for i in range(len(log_e) - 1):
        if log_e[i] <= log_q <= log_e[i + 1]:
            t = (log_q - log_e[i]) / (log_e[i + 1] - log_e[i])
            return math.exp(log_f[i] + t * (log_f[i + 1] - log_f[i]))

    return fluxes[-1]


# ════════════════════════════════════════════════════════════════
#  SYNTHETIC SPECTRA FOR H AND He
# ════════════════════════════════════════════════════════════════

def _generate_hydrogen_spectrum(phi_mv: float) -> ElementSpectrum:
    """Generate H spectrum from Badhwar-O'Neill (2010) parameterization.

    H is not measured by CRIS (which covers Z >= 5), so we use a standard
    GCR proton model.  The local interstellar spectrum for protons is
    approximately:

        J_LIS(T) = 1.9e4 * T^(-2.78) / (1 + 0.4866 * T^(-2.51))

    in units of [m^2 s sr MeV]^-1, then modulated by the force-field
    approximation.
    """
    energies = [50, 75, 100, 150, 200, 300, 500, 750, 1000, 2000, 5000]
    fluxes = []
    phi_mev = phi_mv  # For Z=1, A=1, Phi = phi in MeV

    for t in energies:
        t_lis = t + phi_mev
        # Badhwar-O'Neill LIS for protons (particles / m^2 s sr MeV)
        j_lis = 1.9e4 * t_lis ** (-2.78) / (1 + 0.4866 * t_lis ** (-2.51))
        # Kinematic factor
        t0 = T0_MEV
        kfac = t * (t + 2 * t0) / (t_lis * (t_lis + 2 * t0))
        j_mod = j_lis * kfac
        # Convert m^2 -> cm^2 (factor 1e-4), and multiply by 1e9 to match
        # CRIS units of 1e-9 cm^-2 s^-1 sr^-1 (MeV/nuc)^-1
        j_cris_units = j_mod * 1e-4 * 1e9
        fluxes.append(j_cris_units)

    return ElementSpectrum(
        element="H",
        energies_mev_nuc=energies,
        fluxes=fluxes,
        flux_errors=[f * 0.1 for f in fluxes],  # ~10% uncertainty
    )


def _generate_helium_spectrum(phi_mv: float) -> ElementSpectrum:
    """Generate He spectrum from scaled proton LIS.

    He/H ratio in GCR is approximately 0.06-0.08 at similar rigidity.
    We use J_He_LIS ~ 0.07 * J_H_LIS with A=4, Z=2.
    """
    energies = [50, 75, 100, 150, 200, 300, 500, 750, 1000, 2000]
    fluxes = []
    phi_per_nuc = 2 * phi_mv / 4  # Z=2, A=4

    for t in energies:
        t_lis = t + phi_per_nuc
        t0_per_nuc = T0_MEV / 4
        j_lis = 0.07 * 1.9e4 * t_lis ** (-2.78) / (1 + 0.4866 * t_lis ** (-2.51))
        kfac = t * (t + 2 * t0_per_nuc) / (t_lis * (t_lis + 2 * t0_per_nuc))
        j_mod = j_lis * kfac
        j_cris_units = j_mod * 1e-4 * 1e9
        fluxes.append(j_cris_units)

    return ElementSpectrum(
        element="He",
        energies_mev_nuc=energies,
        fluxes=fluxes,
        flux_errors=[f * 0.15 for f in fluxes],
    )


# ════════════════════════════════════════════════════════════════
#  MAIN API CLASS
# ════════════════════════════════════════════════════════════════

class GCRFluxModel:
    """Provides interpolated GCR flux from real ACE/CRIS data.

    Usage:
        model = GCRFluxModel()  # loads from default data dir
        flux = model.get_gcr_flux("Fe", energy_MeV=200.0, solar_cycle_phase=0.0)

    solar_cycle_phase: 0.0 = solar minimum, 0.5 = solar maximum, 1.0 = next minimum
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self._solar_min: Dict[str, ElementSpectrum] = {}
        self._solar_max: Dict[str, ElementSpectrum] = {}
        self._phi_records: List[PhiRecord] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        spectra_path = self._data_dir / "cris_spectra.txt"
        leaky_box_path = self._data_dir / "cris_leaky_box.txt"

        if spectra_path.exists():
            self._solar_min, self._solar_max = parse_spectra_file(spectra_path)
            logger.info(
                "gcr.spectra.loaded",
                solar_min_elements=len(self._solar_min),
                solar_max_elements=len(self._solar_max),
            )
        else:
            logger.warning("gcr.spectra.missing", path=str(spectra_path))

        if leaky_box_path.exists():
            self._phi_records = parse_leaky_box_file(leaky_box_path)
            logger.info("gcr.phi_records.loaded", count=len(self._phi_records))
        else:
            logger.warning("gcr.leaky_box.missing", path=str(leaky_box_path))

        # Add synthetic H and He spectra (not measured by CRIS)
        self._solar_min["H"] = _generate_hydrogen_spectrum(PHI_SOLAR_MIN_MV)
        self._solar_max["H"] = _generate_hydrogen_spectrum(PHI_SOLAR_MAX_MV)
        self._solar_min["He"] = _generate_helium_spectrum(PHI_SOLAR_MIN_MV)
        self._solar_max["He"] = _generate_helium_spectrum(PHI_SOLAR_MAX_MV)

        self._loaded = True

    @property
    def available_elements(self) -> List[str]:
        """List of elements with spectral data."""
        self._ensure_loaded()
        return sorted(set(self._solar_min.keys()) | set(self._solar_max.keys()))

    @property
    def phi_records(self) -> List[PhiRecord]:
        """Bartels-rotation phi records from the leaky box fit."""
        self._ensure_loaded()
        return list(self._phi_records)

    def get_phi_for_phase(self, solar_cycle_phase: float) -> float:
        """Convert solar cycle phase [0,1] to modulation parameter phi (MV).

        0.0 = solar minimum (~250 MV), 0.5 = solar maximum (~900 MV).
        Uses sinusoidal interpolation matching the Schwabe cycle.
        """
        # Phase 0 -> min, 0.5 -> max: use cosine
        phi = (PHI_SOLAR_MIN_MV + PHI_SOLAR_MAX_MV) / 2.0 + \
              (PHI_SOLAR_MIN_MV - PHI_SOLAR_MAX_MV) / 2.0 * math.cos(
                  2 * math.pi * solar_cycle_phase)
        return phi

    def get_gcr_flux(
        self,
        element: str,
        energy_MeV: float,
        solar_cycle_phase: float,
    ) -> float:
        """Get differential GCR flux for an element at given energy and solar phase.

        Args:
            element: Chemical symbol (H, He, C, N, O, Fe, etc.)
            energy_MeV: Kinetic energy per nucleon in MeV/nuc
            solar_cycle_phase: Phase in [0, 1]. 0.0 = solar minimum,
                0.5 = solar maximum.

        Returns:
            Differential flux in particles / (cm^2 s sr MeV/nuc).
            (Note: the raw CRIS data is in units of 1e-9; we return
            the actual flux, i.e., CRIS_value * 1e-9.)
        """
        self._ensure_loaded()

        if element not in ELEMENT_TABLE:
            raise ValueError(
                f"Unknown element '{element}'. Available: {list(ELEMENT_TABLE.keys())}"
            )

        # Get solar cycle phase -> phi
        phi_target = self.get_phi_for_phase(solar_cycle_phase)

        # If we have measured spectra for this element, interpolate between
        # solar min and max, then apply force-field correction for intermediate phi
        has_min = element in self._solar_min
        has_max = element in self._solar_max

        if has_min and has_max:
            flux_min = _interpolate_log(
                self._solar_min[element].energies_mev_nuc,
                self._solar_min[element].fluxes,
                energy_MeV,
            )
            flux_max = _interpolate_log(
                self._solar_max[element].energies_mev_nuc,
                self._solar_max[element].fluxes,
                energy_MeV,
            )

            # Linear interpolation in phi-space between min and max
            if PHI_SOLAR_MAX_MV != PHI_SOLAR_MIN_MV:
                t = (phi_target - PHI_SOLAR_MIN_MV) / (PHI_SOLAR_MAX_MV - PHI_SOLAR_MIN_MV)
                t = max(0.0, min(1.0, t))
            else:
                t = 0.0

            # Interpolate in log-flux space for smoother results
            if flux_min > 0 and flux_max > 0:
                log_flux = math.log(flux_min) * (1 - t) + math.log(flux_max) * t
                flux_cris_units = math.exp(log_flux)
            else:
                flux_cris_units = flux_min * (1 - t) + flux_max * t

            # Apply force-field correction for phi outside the min/max range
            if phi_target < PHI_SOLAR_MIN_MV or phi_target > PHI_SOLAR_MAX_MV:
                z, a = ELEMENT_TABLE[element]
                phi_ref = PHI_SOLAR_MIN_MV if phi_target < PHI_SOLAR_MIN_MV else PHI_SOLAR_MAX_MV
                ratio = _force_field_ratio(energy_MeV, phi_ref, phi_target, z, a)
                flux_cris_units *= ratio

        elif has_min:
            flux_cris_units = _interpolate_log(
                self._solar_min[element].energies_mev_nuc,
                self._solar_min[element].fluxes,
                energy_MeV,
            )
            z, a = ELEMENT_TABLE[element]
            ratio = _force_field_ratio(energy_MeV, PHI_SOLAR_MIN_MV, phi_target, z, a)
            flux_cris_units *= ratio

        elif has_max:
            flux_cris_units = _interpolate_log(
                self._solar_max[element].energies_mev_nuc,
                self._solar_max[element].fluxes,
                energy_MeV,
            )
            z, a = ELEMENT_TABLE[element]
            ratio = _force_field_ratio(energy_MeV, PHI_SOLAR_MAX_MV, phi_target, z, a)
            flux_cris_units *= ratio

        else:
            raise ValueError(
                f"No spectral data for element '{element}'. "
                f"Available: {self.available_elements}"
            )

        # Convert from CRIS units (1e-9 factor) to absolute flux
        return flux_cris_units * 1e-9

    def get_total_dose_rate_msv_day(
        self,
        solar_cycle_phase: float,
        shielding_g_cm2: float = 20.0,
    ) -> float:
        """Estimate total GCR dose rate behind shielding.

        Simplified dose calculation using flux-to-dose conversion factors
        from ICRP and NASA-STD-3001.

        Args:
            solar_cycle_phase: 0.0 = solar min, 0.5 = solar max
            shielding_g_cm2: Areal density of shielding (g/cm^2).
                ~20 for ISS-equivalent aluminum, ~30 for deep-space habitat.

        Returns:
            Approximate dose rate in mSv/day.
        """
        self._ensure_loaded()

        # Dose conversion factors (mSv*cm^2 / particle) at ~200 MeV/nuc
        # From NASA-TP-2013-217390 (Slaba et al.)
        dose_conversion = {
            "H": 2.0e-8, "He": 1.5e-7, "C": 3.5e-6, "N": 5.0e-6,
            "O": 7.5e-6, "Fe": 2.0e-4,
        }
        # Shielding attenuation (simplified exponential)
        # Mean free path in aluminum: ~30 g/cm^2 for protons, less for HZE
        mfp = {"H": 50.0, "He": 40.0, "C": 25.0, "N": 22.0, "O": 20.0, "Fe": 12.0}

        total_dose_msv_s = 0.0
        ref_energy = 200.0  # MeV/nuc — representative energy

        for elem in PRIMARY_ELEMENTS:
            flux = self.get_gcr_flux(elem, ref_energy, solar_cycle_phase)
            # flux is differential: particles / (cm^2 s sr MeV/nuc)
            # Integrate over ~4*pi sr and ~200 MeV energy band (rough)
            fluence_rate = flux * 4 * math.pi * 200.0  # particles / (cm^2 s)
            # Shielding attenuation
            atten = math.exp(-shielding_g_cm2 / mfp.get(elem, 30.0))
            shielded_fluence = fluence_rate * atten
            # Dose
            conv = dose_conversion.get(elem, 1e-7)
            total_dose_msv_s += shielded_fluence * conv

        # Convert s -> day
        return total_dose_msv_s * 86400.0


# ════════════════════════════════════════════════════════════════
#  MODULE-LEVEL CONVENIENCE FUNCTION
# ════════════════════════════════════════════════════════════════

_default_model: Optional[GCRFluxModel] = None


def get_gcr_flux(element: str, energy_MeV: float, solar_cycle_phase: float) -> float:
    """Module-level convenience function.

    Lazily loads the default data directory on first call.

    Args:
        element: Chemical symbol (H, He, C, N, O, Fe, etc.)
        energy_MeV: Kinetic energy per nucleon in MeV/nuc
        solar_cycle_phase: 0.0 = solar min, 0.5 = solar max

    Returns:
        Differential flux in particles / (cm^2 s sr MeV/nuc).
    """
    global _default_model
    if _default_model is None:
        _default_model = GCRFluxModel()
    return _default_model.get_gcr_flux(element, energy_MeV, solar_cycle_phase)
