"""
Conjunction Prediction — Space Debris Tracking & Collision Assessment

Production-grade implementation of the NASA CARA conjunction assessment pipeline:
  TLE Ingestion → SGP4 Propagation → Smart Sieve Screening → TCA Detection
  → Collision Probability (Foster/Chan/Monte Carlo) → Maneuver Planning → CDM Output
"""

__version__ = "0.1.0"
