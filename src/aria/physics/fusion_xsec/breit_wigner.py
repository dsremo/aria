"""Single-level Breit-Wigner resonance capture (§4.4 of E1 scope).

For an isolated s-wave resonance at energy E₀ with total width Γ and
radiative (γ) partial width Γ_γ, the zero-temperature capture cross
section is (Bell & Glasstone 1970 *Nuclear Reactor Theory* eq. 2-127;
Reuss 2008 *Neutron Physics* eq. 2.69):

    σ_γ(E) = σ_0 · (Γ_γ Γ_n / Γ²) · (Γ/2)² / ((E − E₀)² + (Γ/2)²)   [barn]

where `σ_0 = 4π (ℏ/k)² g_J` is the peak cross section (~10³ barn
for the canonical ²³⁸U s-wave resonances). Doppler broadening is
deferred to the ENDF pipeline (Cullen ψ-χ, §8 of the scope note);
here we expose only the zero-T Lorentzian for unit-level benchmarks.
"""

from __future__ import annotations


def breit_wigner_capture_cross_section_barn(
    energy_ev: float,
    resonance_energy_ev: float,
    total_width_ev: float,
    neutron_width_ev: float,
    gamma_width_ev: float,
    peak_sigma_0_barn: float,
) -> float:
    """Zero-temperature single-level Breit-Wigner capture σ_γ(E).

    σ_γ(E) = σ_0 · (Γ_γ Γ_n / Γ²) · (Γ/2)² / ((E − E_0)² + (Γ/2)²)

    The prefactor `σ_0 · Γ_γ Γ_n / Γ²` is the peak capture cross
    section at E = E₀; the Lorentzian kernel is the unit-area
    resonance lineshape (FWHM = Γ).

    Args:
        energy_ev: neutron incident energy E (eV, positive).
        resonance_energy_ev: E_0 (eV, positive).
        total_width_ev: Γ = Γ_n + Γ_γ + ... (eV, positive).
        neutron_width_ev: Γ_n elastic neutron width (eV, non-negative).
        gamma_width_ev: Γ_γ radiative width (eV, non-negative).
        peak_sigma_0_barn: σ_0 peak resonance cross section (barn).

    Returns:
        σ_γ(E) in barn.
    """
    if energy_ev <= 0.0:
        raise ValueError("energy_ev must be positive")
    if resonance_energy_ev <= 0.0:
        raise ValueError("resonance_energy_ev must be positive")
    if total_width_ev <= 0.0:
        raise ValueError("total_width_ev must be positive")
    if neutron_width_ev < 0.0 or gamma_width_ev < 0.0:
        raise ValueError("partial widths must be non-negative")
    if peak_sigma_0_barn < 0.0:
        raise ValueError("peak_sigma_0_barn must be non-negative")
    half_gamma = 0.5 * total_width_ev
    delta_e = energy_ev - resonance_energy_ev
    branching = gamma_width_ev * neutron_width_ev / (total_width_ev * total_width_ev)
    lorentzian = (half_gamma * half_gamma) / (delta_e * delta_e + half_gamma * half_gamma)
    return peak_sigma_0_barn * branching * lorentzian
