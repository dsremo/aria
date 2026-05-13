# ARIA Honesty Audit — What's Real vs What's Fake

## Summary

131 lines of fake random-based simulation vs 167 lines of real physics equations.
Ratio: 0.8:1 (better than expected, but still significant fakery).

## What IS Real Physics

| Module | What's Real | Source |
|--------|-------------|--------|
| basilisk_runner.py | Full 6-DOF orbital mechanics | Basilisk 2.10.0 (peer-reviewed) |
| shield_system.py | Hoang erosion model, Lorentz deflection, Stefan-Boltzmann | Hoang et al., CERN SR2S |
| thermal_management.py | Stefan-Boltzmann radiator: P = εσAT⁴ | Thermodynamics |
| braking_architecture.py | Forward staged sail, Tsiolkovsky, magsail F=Cd·ρ·v²·A | Forward 1984, Zubrin 1991 |
| food_synthesis.py | ISM density model, Sabatier stoichiometry | Cai 2021, NASA |
| first_1000_days.py | NASA BVAD mass balance (0.84 kg O2/person/day etc.) | NASA BVAD |
| biology_social.py | Weibull failure: P = 1-exp(-(t/η)^β) | Reliability engineering |
| remaining_systems.py | Wright's formula for inbreeding, stellar proper motion | Population genetics |

## What IS Fake (random() < magic_number)

| Module | What's Fake | Why It's Wrong |
|--------|-------------|----------------|
| interstellar_challenges.py | `if random() < 0.02: bioreactor contamination` | Real contamination depends on sterilization protocols, not dice rolls |
| defense.py | `detected = random() < tracking_accuracy` | Real detection uses radar cross-section, signal-to-noise ratio |
| fire_safety.py | `if random() < fire_risk_level` | Real fire modeling uses CFD, fuel load analysis, ignition sources |
| governance.py | `if random() < 0.05: constitutional_crisis` | Social dynamics aren't random — they depend on resource scarcity, leadership |
| medical_robotics.py | `needs_surgery = random() < probability` | Real medical incidence rates are epidemiological, not random |
| manufacturing.py | `if random() < failure_prob: printer fails` | Real failure analysis uses stress cycles, thermal fatigue, material properties |

## What We're Honest About

1. **We cannot simulate what hasn't been built.** Fusion propulsion, closed-loop ECLSS for 1000 years, interstellar flight — none of this exists. Our simulation explores the problem space, it doesn't solve it.

2. **Random events are placeholders.** Every `random() < 0.02` should eventually be replaced by a model that calculates the ACTUAL probability from physical parameters.

3. **No validation against reality.** We validated against NASA data where possible (BVAD, Voyager RTG, ISS water recycling), but most of our models have never been compared to real-world data.

4. **This is a research prototype.** It catalogs ~400 problems a generation ship must solve and provides a framework for exploring them. It is NOT flight software.

## What This Project Actually IS

- A comprehensive problem catalog (384 expert-identified issues)
- A framework for thinking about interstellar travel
- A simulation that shows relative importance of subsystems
- A teaching tool about spacecraft engineering
- A starting point for serious engineering analysis

## What This Project IS NOT

- Validated engineering simulation
- Flight-qualified software
- A replacement for actual aerospace engineering
- Proof that interstellar travel is feasible
