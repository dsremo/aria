"""Physics cross-check scenario harness (Phase 4 item — regression).

Each module in this package picks a canonical mission scenario (e.g.
1000-year interstellar cruise, tokamak disruption event, habitat
fatigue over 50 years) and invokes primitives from multiple physics
pods to verify cross-pod invariants:

- quantities that flow from one pod into another must be consistent;
- conservative upper bounds from different pods must agree when the
  same physical effect is computed two different ways;
- handbook regime gates (Bo vs gravity, TBR vs Abdou, CMG saturation
  vs h_max) must fire in the same regime the owning pod advertises.

The scenarios do NOT touch the generation_ship engine or
simulator.py — they operate purely on the physics primitive layer so
that a regression here isolates a physics change rather than an
engine-integration issue.
"""
