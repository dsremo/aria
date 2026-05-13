"""Stellar contamination correction for transit transmission spectroscopy.

P1 FIX (Madhusudhan critique): "The transit light source effect (TLSE) from
unocculted stellar heterogeneities (spots, faculae) can mimic or mask
atmospheric spectral features. Ignoring it inflates false positive rates
for biosignatures, particularly in the 1-5 μm range for M-dwarf hosts."

The contamination spectrum is:
    F_contaminated(λ) = F_true(λ) × C(λ)

where the contamination factor is:

    C(λ) = [1 - f_spot × (1 - F_spot/F_phot) - f_fac × (1 - F_fac/F_phot)]⁻¹

  f_spot: filling factor of unocculted stellar spots [0, 1]
  f_fac:  filling factor of unocculted faculae [0, 1]
  F_spot, F_fac, F_phot: spectral flux from spots, faculae, photosphere
                         (approximated by blackbody at T_spot, T_fac, T_eff)

Reference:
  Rackham et al. (2018), ApJ 853:122
  Wakeford et al. (2019), AJ 157:11
  Apai et al. (2018), ApJ 873:L1 (K2-18b relevant)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

logger = structlog.get_logger()

# Physical constants (CODATA 2018: Tiesinga et al. 2021 Rev Mod Phys 93 025010)
H = 6.62607015e-34   # Planck constant (J·s) — CODATA 2018 exact
C_LIGHT = 2.99792458e8 # Speed of light (m/s) — CODATA 2018 exact
K_B = 1.380649e-23   # Boltzmann constant (J/K) — CODATA 2018 exact


@dataclass(frozen=True)
class StellarContaminationResult:
    """Result of stellar contamination correction."""

    contamination_factor: np.ndarray       # C(λ) — multiplicative correction
    corrected_spectrum: np.ndarray         # F_true = F_obs / C(λ)
    contamination_slope_ppm_per_um: float  # spectral slope of contamination
    max_contamination_pct: float           # max |C - 1| × 100%
    is_significant: bool                   # True if contamination > 50 ppm anywhere
    wavelengths_um: np.ndarray
    spot_filling_factor: float
    fac_filling_factor: float
    t_eff_k: float
    t_spot_k: float
    t_fac_k: float


def planck_function(wavelength_um: np.ndarray, temperature_k: float) -> np.ndarray:
    """Planck spectral radiance B_λ(T) in W/(m²·sr·m).

    B_λ(T) = (2hc²/λ⁵) × 1/(exp(hc/λkT) - 1)

    Args:
        wavelength_um: Wavelength grid in micrometers.
        temperature_k: Blackbody temperature in Kelvin.

    Returns:
        Planck function values (arbitrary scaling, used as ratios).
    """
    lam = wavelength_um * 1e-6  # μm → m
    x = H * C_LIGHT / (lam * K_B * temperature_k)
    # Clamp to avoid overflow in exp
    x = np.minimum(x, 700.0)
    return (2.0 * H * C_LIGHT**2 / lam**5) / (np.exp(x) - 1.0)


def compute_contamination_factor(
    wavelengths_um: np.ndarray,
    t_eff_k: float,
    t_spot_k: float | None = None,
    t_fac_k: float | None = None,
    spot_filling_factor: float = 0.0,
    fac_filling_factor: float = 0.0,
) -> np.ndarray:
    """Compute the stellar contamination factor C(λ).

    C(λ) = [1 - f_spot×(1 - B_λ(T_spot)/B_λ(T_eff))
              - f_fac ×(1 - B_λ(T_fac) /B_λ(T_eff))]⁻¹

    For K2-18 (M2.5V):
      T_eff ≈ 3500K, T_spot ≈ 3000K, f_spot ≈ 0.10-0.30 (active M dwarf)
      T_fac ≈ 3800K, f_fac  ≈ 0.05-0.15

    Args:
        wavelengths_um: Wavelength grid in micrometers.
        t_eff_k: Stellar effective temperature (K).
        t_spot_k: Spot temperature (K). Defaults to t_eff - 200K.
        t_fac_k: Faculae temperature (K). Defaults to t_eff + 100K.
        spot_filling_factor: f_spot ∈ [0, 1]. Fraction of unoccluded disk in spots.
        fac_filling_factor: f_fac ∈ [0, 1]. Fraction of unoccluded disk in faculae.

    Returns:
        Contamination factor C(λ) array (≥1 in spot-dominated regions).
    """
    if t_spot_k is None:
        t_spot_k = t_eff_k - 200.0  # ESTIMATE — ΔT_spot ≈ −200 K default (Rackham 2018 ApJ 853 122 Table 2)
    if t_fac_k is None:
        t_fac_k = t_eff_k + 100.0   # ESTIMATE — ΔT_fac ≈ +100 K default (Rackham 2018 ApJ 853 122)

    t_spot_k = max(t_spot_k, 1000.0)  # physical lower bound
    t_fac_k = max(t_fac_k, t_eff_k)

    b_phot = planck_function(wavelengths_um, t_eff_k)
    b_phot = np.where(b_phot > 0, b_phot, 1e-300)

    # Spot contribution (cooler → less flux at short wavelengths)
    spot_term = spot_filling_factor * (1.0 - planck_function(wavelengths_um, t_spot_k) / b_phot)

    # Faculae contribution (hotter → more flux at short wavelengths)
    fac_term = fac_filling_factor * (1.0 - planck_function(wavelengths_um, t_fac_k) / b_phot)

    denominator = 1.0 - spot_term - fac_term
    # Avoid division by zero or negative (unphysical — would mean 100% coverage)
    denominator = np.where(denominator > 0.01, denominator, 0.01)

    return 1.0 / denominator


def correct_stellar_contamination(
    wavelengths_um: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,  # noqa: ARG001
    t_eff_k: float,
    spot_filling_factor: float = 0.0,
    fac_filling_factor: float = 0.0,
    t_spot_k: float | None = None,
    t_fac_k: float | None = None,
) -> StellarContaminationResult:
    """Apply stellar contamination correction to a transmission spectrum.

    Divides the observed spectrum by C(λ) to recover the true planetary
    transmission spectrum. If filling factors are zero, returns the input
    unchanged (no-op for clean stars).

    Args:
        wavelengths_um: Wavelength grid (μm).
        flux: Observed transmission spectrum (R_p/R_star)².
        flux_err: Photometric uncertainties.
        t_eff_k: Stellar effective temperature (K).
        spot_filling_factor: Fraction of unocculted disk covered by spots [0, 1].
        fac_filling_factor: Fraction of unocculted disk covered by faculae [0, 1].
        t_spot_k: Spot temperature (K). Auto-estimated if None.
        t_fac_k: Faculae temperature (K). Auto-estimated if None.

    Returns:
        StellarContaminationResult with corrected spectrum and diagnostics.
    """
    c = compute_contamination_factor(
        wavelengths_um, t_eff_k, t_spot_k, t_fac_k,
        spot_filling_factor, fac_filling_factor,
    )

    corrected = flux / c
    max_contamination_pct = float(np.max(np.abs(c - 1.0))) * 100.0
    is_significant = max_contamination_pct > 50e-4  # > 50 ppm

    # Contamination slope: linear fit of (C - 1) vs wavelength in ppm/μm
    slope_ppm = 0.0
    if len(wavelengths_um) > 2:
        try:
            c_ppm = (c - 1.0) * 1e6
            coeffs = np.polyfit(wavelengths_um, c_ppm, 1)
            slope_ppm = float(coeffs[0])
        except Exception:  # noqa: S110, BLE001
            pass

    if is_significant:
        logger.warning(
            "stellar_contamination_significant",
            max_contamination_pct=round(max_contamination_pct, 2),
            slope_ppm_per_um=round(slope_ppm, 1),
            spot_ff=spot_filling_factor,
            fac_ff=fac_filling_factor,
            msg="Stellar contamination > 50 ppm — correction strongly recommended",
        )

    return StellarContaminationResult(
        contamination_factor=c,
        corrected_spectrum=corrected,
        contamination_slope_ppm_per_um=slope_ppm,
        max_contamination_pct=max_contamination_pct,
        is_significant=is_significant,
        wavelengths_um=wavelengths_um,
        spot_filling_factor=spot_filling_factor,
        fac_filling_factor=fac_filling_factor,
        t_eff_k=t_eff_k,
        t_spot_k=t_spot_k or (t_eff_k - 200.0),
        t_fac_k=t_fac_k or (t_eff_k + 100.0),
    )


def estimate_spot_params_from_stellar_type(
    stellar_type: str,
) -> dict[str, float]:
    """Return typical spot/faculae parameters for a given stellar spectral type.

    Based on Rackham et al. (2018) Table 2 and Stelzer et al. (2016) statistics.

    Args:
        stellar_type: Spectral type, e.g. "M2", "K5", "G2", "F8".

    Returns:
        Dict with keys: t_eff_k, t_spot_k, t_fac_k, spot_ff, fac_ff.
    """
    st = stellar_type.upper().strip()
    primary = st[0] if st else "G"

    defaults: dict[str, dict[str, float]] = {
        "F": {"t_eff_k": 6500, "t_spot_k": 5900, "t_fac_k": 6700, "spot_ff": 0.01, "fac_ff": 0.10},
        "G": {"t_eff_k": 5800, "t_spot_k": 5100, "t_fac_k": 6000, "spot_ff": 0.02, "fac_ff": 0.15},
        "K": {"t_eff_k": 5000, "t_spot_k": 4300, "t_fac_k": 5200, "spot_ff": 0.05, "fac_ff": 0.20},
        "M": {"t_eff_k": 3500, "t_spot_k": 3000, "t_fac_k": 3700, "spot_ff": 0.15, "fac_ff": 0.10},
    }

    params = defaults.get(primary, defaults["G"])

    # Subtype correction for M dwarfs (M0-M9 spans 3800K-2300K)
    if primary == "M" and len(st) >= 2:
        try:
            subtype = int(st[1])
            params = dict(params)
            params["t_eff_k"] = 3800.0 - subtype * 140.0
            params["t_spot_k"] = params["t_eff_k"] - 400.0
            params["t_fac_k"] = params["t_eff_k"] + 100.0
            # Later M dwarfs are more magnetically active
            params["spot_ff"] = min(0.05 + subtype * 0.025, 0.40)
        except ValueError:
            pass

    return params
