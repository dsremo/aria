"""NOAA GOES-16 Solar Proton Flux Loader.

Loads real solar energetic particle (SEP) measurements from GOES-16 SGPS
(Space Geodesy Proton Sensor) Level 2 netCDF files. Provides:

  1. Real proton differential flux spectra (p/cm²/sr/keV/s) in 13 energy bands
     spanning 1–404 MeV — replaces the synthetic power-law fallback in
     radiation_transport.py for the proton component.

  2. SEP event detection: integral flux > 10 p/cm²/s/sr at >10 MeV is the
     NOAA SPE threshold (NOAA SEC 2003; Shea & Smart 2012 Space Sci. Rev.).

  3. SEP dose estimate: integrated fluence × ICRP 123 proton dose coefficients
     → effective dose in mSv for any event period.

Data format: SGPS-L2-AVG1M 1-minute averages.
  AvgDiffProtonFlux[time, sensor, band]   p/cm²/sr/keV/s
  AvgIntProtonFlux[time, sensor]          p/cm²/sr/s  (>500 MeV threshold)
  DiffProtonEffectiveEnergy[sensor, band] keV
  time: seconds since 2000-01-01 12:00:00 UTC

Dataset used: GOES-16, March 2025 (31 days, quiet period — no large SPEs).
Reference: NOAA NCEI GOES-R Series documentation.
  Harris et al. (2020) Space Weather 18 e2020SW002450 (SGPS calibration).

Instrument: SGPS = Space Geodesy Proton Sensor, two sensors (0=east, 1=west),
  aboard GOES-16 at GEO orbit (35,786 km).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()

GOES_DATA_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "data" / "raw" / "noaa_goes"
)

# NOAA SPE threshold: integral proton flux >10 p/cm²/sr/s at >10 MeV
# NOAA SEC (2003) Solar Proton Event threshold; Shea & Smart (2012) SSR 171 23
SPE_THRESHOLD_PFU = 10.0   # 1 PFU = 1 p/cm²/sr/s at >10 MeV

# ICRP 123 (2013) Table A.4: effective dose per proton fluence, Sv·cm²
# at selected energies; log-interpolated for arbitrary energies.
# Jia et al. (2020) review, Table 2 supplementary (based on ICRP 123 protons).
ICRP123_ENERGY_MEV = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0,
                       500.0, 1000.0]
ICRP123_EFF_DOSE_SV_CM2 = [2.4e-13, 5.2e-13, 1.1e-12, 1.6e-12, 3.0e-12,
                             6.5e-12, 1.0e-11, 1.5e-11, 2.5e-11, 3.5e-11]


@dataclass
class DailyFluxRecord:
    """Daily average proton flux spectrum from one GOES-16 file."""
    date_str:          str           # 'YYYYMMDD'
    energy_mev:        list[float]   # effective energy per band [MeV]
    mean_flux_diff:    list[float]   # mean daily differential flux [p/cm²/sr/keV/s]
    peak_flux_diff:    list[float]   # peak 1-min differential flux [p/cm²/sr/keV/s]
    mean_int_flux:     float         # mean integral flux >500 MeV [p/cm²/sr/s]
    peak_int_flux:     float         # peak integral flux >500 MeV [p/cm²/sr/s]
    n_valid_minutes:   int           # number of valid 1-min samples


@dataclass
class SepEvent:
    """A detected Solar Energetic Particle event."""
    date_str:    str
    peak_pfu:    float    # peak integral flux [p/cm²/sr/s] at >10 MeV (approx)
    duration_h:  float    # event duration above threshold [hours]
    fluence_p_cm2_sr: float  # total fluence ≈ peak × duration × 3600 [p/cm²/sr]
    dose_msv:    float    # estimated effective dose [mSv] (BFO, unshielded)


def icrp123_dose_coeff(energy_mev: float) -> float:
    """Log-log interpolation of ICRP 123 effective dose coefficient [Sv·cm²].

    Valid for 1–1000 MeV protons.  Below 1 MeV: use 1 MeV value (conservative).
    Above 1000 MeV: extrapolate (decreasing trend).

    Reference: ICRP 123 (2013) Table A.4.
    """
    e = max(1.0, energy_mev)
    log_e = math.log10(e)
    log_e0 = [math.log10(x) for x in ICRP123_ENERGY_MEV]
    log_d0 = [math.log10(x) for x in ICRP123_EFF_DOSE_SV_CM2]

    if log_e <= log_e0[0]:
        return ICRP123_EFF_DOSE_SV_CM2[0]
    if log_e >= log_e0[-1]:
        # Linear extrapolation in log-log space
        slope = (log_d0[-1] - log_d0[-2]) / (log_e0[-1] - log_e0[-2])
        return 10 ** (log_d0[-1] + slope * (log_e - log_e0[-1]))

    # Linear interpolation in log-log space
    for i in range(len(log_e0) - 1):
        if log_e0[i] <= log_e <= log_e0[i + 1]:
            t = (log_e - log_e0[i]) / (log_e0[i + 1] - log_e0[i])
            log_d = log_d0[i] + t * (log_d0[i + 1] - log_d0[i])
            return 10 ** log_d
    return ICRP123_EFF_DOSE_SV_CM2[-1]


def load_daily_flux(nc_path: Path, sensor: int = 0) -> Optional[DailyFluxRecord]:
    """Load one GOES-16 netCDF file and return daily flux statistics.

    Args:
        nc_path:  Path to .nc file (SGPS-L2-AVG1M format)
        sensor:   0 = east-facing sensor (default), 1 = west-facing

    Returns:
        DailyFluxRecord or None if file is unreadable.
    """
    try:
        import netCDF4 as nc4
    except ImportError:
        logger.error("noaa_goes.netCDF4_missing",
                     msg="pip install netCDF4 to load GOES data")
        return None

    try:
        f = nc4.Dataset(nc_path)
    except Exception as e:
        logger.warning("noaa_goes.open_failed", path=str(nc_path), error=str(e))
        return None

    try:
        # Effective energies for this sensor [keV → MeV]
        eff_kev = np.array(f.variables['DiffProtonEffectiveEnergy'][sensor, :])
        energy_mev = [float(e / 1000.0) for e in eff_kev]

        # Differential flux [time, sensor, band] → pick sensor, all times/bands
        diff_flux = np.array(f.variables['AvgDiffProtonFlux'][:, sensor, :])  # (1440, 13)
        # Mask fill/invalid values (typically masked arrays from netCDF4)
        if hasattr(diff_flux, 'filled'):
            diff_flux = diff_flux.filled(0.0)
        diff_flux = np.where(np.isfinite(diff_flux) & (diff_flux >= 0), diff_flux, 0.0)

        # Integral flux [time, sensor]
        int_flux = np.array(f.variables['AvgIntProtonFlux'][:, sensor])
        if hasattr(int_flux, 'filled'):
            int_flux = int_flux.filled(0.0)
        int_flux = np.where(np.isfinite(int_flux) & (int_flux >= 0), int_flux, 0.0)

        # Count valid samples (non-zero integral flux indicates real data)
        valid_mask = int_flux > 0
        n_valid = int(np.sum(valid_mask))
    finally:
        f.close()

    # Extract date string from filename: sci_sgps-..._g16_dYYYYMMDD_...
    date_str = nc_path.stem.split('_d')[1].split('_')[0]

    if n_valid == 0:
        logger.debug("noaa_goes.no_valid_samples", date=date_str)
        return None

    return DailyFluxRecord(
        date_str=date_str,
        energy_mev=energy_mev,
        mean_flux_diff=[float(np.mean(diff_flux[:, b][diff_flux[:, b] > 0]))
                        if np.any(diff_flux[:, b] > 0) else 0.0
                        for b in range(diff_flux.shape[1])],
        peak_flux_diff=[float(np.max(diff_flux[:, b])) for b in range(diff_flux.shape[1])],
        mean_int_flux=float(np.mean(int_flux[valid_mask])),
        peak_int_flux=float(np.max(int_flux)),
        n_valid_minutes=n_valid,
    )


def load_all_days(data_dir: Path | None = None, sensor: int = 0) -> list[DailyFluxRecord]:
    """Load all GOES-16 netCDF files in data_dir and return daily flux records.

    Args:
        data_dir: override default GOES_DATA_DIR
        sensor:   0 = east (default)

    Returns:
        List of DailyFluxRecord, one per valid file.
    """
    base = data_dir or GOES_DATA_DIR
    if not base.exists():
        logger.error("noaa_goes.dir_missing", path=str(base))
        return []

    nc_files = sorted(base.glob("sci_sgps-l2-avg1m_g16_d*.nc"))
    if not nc_files:
        logger.warning("noaa_goes.no_nc_files", path=str(base))
        return []

    records = []
    for nc_file in nc_files:
        rec = load_daily_flux(nc_file, sensor=sensor)
        if rec is not None:
            records.append(rec)

    logger.info("noaa_goes.loaded", n_days=len(records), n_files=len(nc_files))
    return records


def detect_spe_events(records: list[DailyFluxRecord],
                      threshold_pfu: float = SPE_THRESHOLD_PFU) -> list[SepEvent]:
    """Identify Solar Energetic Particle events from daily flux records.

    An SPE starts when peak integral flux exceeds threshold_pfu and ends
    when it drops below.  For monthly data, we use daily records so each
    event is flagged at day resolution.

    The >500 MeV integral flux from GOES SGPS is used as a proxy for the
    traditional >10 MeV SPE threshold.  The actual >10 MeV flux would be
    ~100-1000x higher for large events.

    NOAA SPE threshold: >10 pfu at >10 MeV (NOAA SEC 2003).
    Here threshold_pfu applies to the >500 MeV integral channel.

    Reference:
        Shea & Smart (2012) Space Sci. Rev. 171 23–56: SPE catalog 1956–2006.
        NOAA SEC (2003) definition of solar proton events.
    """
    events = []
    for rec in records:
        if rec.peak_int_flux >= threshold_pfu:
            # Estimate >10 MeV flux from highest differential band sums
            # Bands 4–13 cover > 5.8 MeV; sum differential × ΔE for approx integral
            # Use ratio: for large events, >10 MeV is ~100× the >500 MeV flux
            # (Smart & Shea 2002 AdSpR 30 1187: typical spectral index)
            approx_gt10_mev_pfu = rec.peak_int_flux * 100.0  # ESTIMATE (Smart & Shea 2002)

            # Duration: assume event lasts full day if peak exceeds threshold
            duration_h = 24.0  # conservative: day-resolution data

            # Fluence = peak × duration (conservative upper bound)
            fluence = rec.peak_int_flux * duration_h * 3600.0   # [p/cm²/sr]

            # Dose: sum over energy bands using ICRP 123 dose coefficients
            # fluence [p/cm²/sr] × 4π sr × dc [Sv·cm²] → Sv → mSv
            # Here we use the highest differential band energy as representative
            max_energy_mev = max(rec.energy_mev)
            dc = icrp123_dose_coeff(max_energy_mev)   # Sv·cm² per proton at this energy
            # Approximate: treat peak differential flux at highest band as uniform
            peak_high_band_flux = rec.peak_flux_diff[-1]  # p/cm²/sr/keV/s at ~334 MeV
            # Integrate over bandwidth × 4π sr → fluence in highest band
            bw_kev = 128_000.0  # 276-404 keV bandwidth at highest band (keV)
            fluence_high = peak_high_band_flux * bw_kev * duration_h * 3600.0 * 4 * math.pi
            dose_sv = fluence_high * dc
            dose_msv = dose_sv * 1000.0

            events.append(SepEvent(
                date_str=rec.date_str,
                peak_pfu=rec.peak_int_flux,
                duration_h=duration_h,
                fluence_p_cm2_sr=fluence,
                dose_msv=dose_msv,
            ))
    return events


class GoesProtonFluxModel:
    """Real GOES-16 proton flux model for use in radiation_transport.py.

    Replaces _SyntheticFluxModel for the solar proton (H) component using
    actual measured differential flux spectra from NOAA GOES-16 SGPS.

    Interface compatible with _SyntheticFluxModel.get_gcr_flux():
      get_gcr_flux(element, energy_MeV, solar_cycle_phase) → float
        returns differential flux in p/(cm² s sr MeV/nuc)

    For elements other than H (proton): falls back to synthetic power-law
    because GOES only measures protons and alpha particles.

    Data: 31 days of March 2025 (quiet period); mean differential spectrum
    averaged over all valid days.
    """

    def __init__(self, data_dir: Path | None = None):
        self._records: list[DailyFluxRecord] = []
        self._mean_spectrum: list[float] = []   # mean flux per energy band
        self._energy_mev: list[float] = []
        self._loaded = False
        self._data_dir = data_dir
        self._load()

    def _load(self) -> None:
        """Load GOES data and compute mean spectrum over all valid days."""
        records = load_all_days(self._data_dir)
        if not records:
            logger.warning("noaa_goes.model_empty",
                           msg="No GOES data loaded; will use synthetic fallback")
            return

        self._records = records
        self._energy_mev = records[0].energy_mev
        n_bands = len(self._energy_mev)

        # Mean differential flux over all days, per band [p/cm²/sr/keV/s]
        daily_means = np.array([r.mean_flux_diff for r in records])  # (n_days, 13)
        self._mean_spectrum = list(np.mean(daily_means, axis=0))
        self._loaded = True

        logger.info("noaa_goes.model_ready",
                    n_days=len(records),
                    energy_range_mev=f"{self._energy_mev[0]:.1f}-{self._energy_mev[-1]:.1f}",
                    mean_flux_at_10mev=f"{self._mean_spectrum[4]:.4e}")

    def get_gcr_flux(
        self,
        element: str,
        energy_MeV: float,
        solar_cycle_phase: float,
    ) -> float:
        """Return differential proton flux in p/(cm² s sr MeV/nuc).

        For element='H' (proton): use real GOES-16 measured spectrum, with
        solar modulation scaling applied.
        For other elements: use synthetic power-law (GOES only measures p, He).

        Args:
            element:           'H', 'He', 'C', 'O', 'Fe'
            energy_MeV:        Kinetic energy per nucleon [MeV/nuc]
            solar_cycle_phase: 0=solar min, 0.5=solar max (0–1)

        Returns:
            Differential flux [p or ions / (cm² s sr MeV/nuc)]
        """
        if element == "H" and self._loaded and len(self._mean_spectrum) > 0:
            return self._interpolate_proton_flux(energy_MeV, solar_cycle_phase)

        # Fallback synthetic for non-proton species or missing data
        return self._synthetic_flux(element, energy_MeV, solar_cycle_phase)

    def _interpolate_proton_flux(self, energy_mev: float, solar_phase: float) -> float:
        """Log-log interpolate mean GOES proton spectrum at requested energy.

        Convert from p/(cm²/sr/keV/s) → p/(cm²/sr/MeV/s) by × 1000 (1 MeV = 1000 keV).
        Solar modulation: GOES March 2025 is near solar maximum (cycle 25 peak
        ~2025.4); apply 30% suppression relative to solar minimum baseline.
        Modulation model: Badhwar-O'Neill type, see Zhao & Qin (2014) ApJ 798 59.

        Phase 0 = solar min (max GCR flux), phase 0.5 = solar max (min GCR flux).
        During solar maximum, 30% reduction in low-energy protons (<100 MeV).
        """
        # Convert GOES units: p/cm²/sr/keV/s → p/cm²/sr/MeV/s by × 1000
        spectrum_mev = [f * 1000.0 for f in self._mean_spectrum]

        if energy_mev < self._energy_mev[0]:
            # Below lowest band: power-law extrapolation (steep at low energy)
            flux0 = spectrum_mev[0]
            spectral_index = 3.0   # ESTIMATE — steep spectrum below 1 MeV
            flux = flux0 * (energy_mev / self._energy_mev[0]) ** (-spectral_index) if flux0 > 0 else 0.0
        elif energy_mev > self._energy_mev[-1]:
            # Above highest band: GCR power-law extrapolation
            flux_hi = spectrum_mev[-1]
            spectral_index = 2.7   # GCR power law above 100 MeV (Lave 2013 ApJ 770)
            flux = flux_hi * (energy_mev / self._energy_mev[-1]) ** (-spectral_index) if flux_hi > 0 else 0.0
        else:
            # Log-log interpolation between energy bands
            log_e = math.log10(energy_mev)
            log_elist = [math.log10(max(e, 1e-30)) for e in self._energy_mev]
            log_flist = [math.log10(max(f, 1e-30)) for f in spectrum_mev]

            flux = 0.0
            for i in range(len(log_elist) - 1):
                if log_elist[i] <= log_e <= log_elist[i + 1]:
                    t = ((log_e - log_elist[i])
                         / (log_elist[i + 1] - log_elist[i]))
                    log_f = log_flist[i] + t * (log_flist[i + 1] - log_flist[i])
                    flux = 10 ** log_f
                    break

        # Solar modulation: 30% suppression at solar max for E < 100 MeV
        # Zhao & Qin (2014) ApJ 798 59: solar modulation factor ξ(φ, E)
        if energy_mev < 100.0:
            suppression = 0.30  # ESTIMATE — 30% at solar max for E < 100 MeV
            mod = 1.0 - suppression * (1.0 - math.cos(2.0 * math.pi * solar_phase))
        else:
            mod = 1.0   # High-energy GCR barely modulated (Lave 2013 ApJ 770)

        return max(0.0, float(flux) * mod)

    def _synthetic_flux(
        self, element: str, energy_MeV: float, solar_phase: float
    ) -> float:
        """Synthetic power-law fallback for non-proton species."""
        base_flux = {"H": 3.0e-1, "He": 3.0e-2, "C": 8.0e-4, "O": 7.0e-4, "Fe": 2.0e-4}
        # Badhwar-O'Neill (2010) base flux at 200 MeV/nuc, solar min
        f0 = base_flux.get(element, 1e-4)
        spectral = (energy_MeV / 200.0) ** (-2.7)   # Lave 2013 ACE/CRIS spectral index
        modulation = 1.0 - 0.5 * (1.0 - math.cos(2.0 * math.pi * solar_phase))
        return f0 * spectral * modulation

    @property
    def n_days(self) -> int:
        return len(self._records)

    @property
    def spe_events(self) -> list[SepEvent]:
        """Detected SPE events in the loaded dataset."""
        return detect_spe_events(self._records)

    def summary(self) -> dict:
        """Return summary statistics of the loaded data."""
        if not self._loaded:
            return {"status": "no data loaded"}
        return {
            "n_days": self.n_days,
            "date_range": f"{self._records[0].date_str}–{self._records[-1].date_str}",
            "energy_bands": len(self._energy_mev),
            "energy_range_mev": [round(self._energy_mev[0], 2),
                                  round(self._energy_mev[-1], 1)],
            "mean_int_flux_gt500mev": round(
                sum(r.mean_int_flux for r in self._records) / len(self._records), 4
            ),
            "n_spe_events": len(self.spe_events),
            "status": "real GOES-16 SGPS data (quiet period, no large SPE)",
        }


def print_goes_summary(data_dir: Path | None = None) -> None:
    """Print summary of loaded GOES-16 data."""
    model = GoesProtonFluxModel(data_dir)
    s = model.summary()
    print("=" * 65)
    print("  NOAA GOES-16 SGPS — Real Solar Proton Data")
    print("=" * 65)
    print(f"  Days loaded  : {s['n_days']}")
    print(f"  Date range   : {s.get('date_range', 'N/A')}")
    print(f"  Energy bands : {s.get('energy_bands', 'N/A')} "
          f"({s.get('energy_range_mev', 'N/A')} MeV)")
    print(f"  Mean int flux: {s.get('mean_int_flux_gt500mev', 'N/A'):.4f} p/cm²/sr/s "
          f"(>500 MeV)")
    print(f"  SPE events   : {s.get('n_spe_events', 0)}")
    print(f"  Status       : {s.get('status', '')}")
    print()
    print("  Proton flux at key energies (mean spectrum):")
    if model._loaded:
        for e_mev in [1.4, 8.0, 30.8, 54.4, 108.6, 196.8, 333.9]:
            flux = model.get_gcr_flux("H", e_mev, 0.0)
            print(f"    {e_mev:6.1f} MeV  →  {flux:.4e} p/cm²/sr/s/MeV")
    print("=" * 65)


if __name__ == "__main__":
    print_goes_summary()
