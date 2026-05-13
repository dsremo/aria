"""Continuous integration of new published research.

ARIA's autonomy + safety architecture is informed by the published
literature on spacecraft autonomy, ML safety, BLSS, propulsion,
radiation, etc. The literature is large and moves monthly.
Without an automated way to track it, the project drifts away from
the state of the art.

This subpackage tracks relevant arXiv categories and surfaces new
papers per ARIA subsystem. Designed to run as a daily cron + emit
a digest to ``data/runtime/research/`` for the operator UI.

Subsystem topic map (see ``filters.py``):

  autonomy        — cs.RO + cs.AI, keywords spacecraft / satellite / autonomy
  ml_safety       — cs.LG + cs.AI, keywords alignment / RLHF / robustness
  guidance_navigation — cs.RO + math.OC, keywords MPC / SCP / Kalman
  life_support    — q-bio.OT + biorxiv mirror, keywords MELiSSA / ECLSS
  propulsion      — physics.flu-dyn + space-grade, keywords thrust / hall
  radiation       — physics.med-ph, keywords GCR / SEP / shielding
  conjunction     — astro-ph.EP / astro-ph.IM, keywords TLE / collision

Each filter produces a list of recent matching papers; the digest
aggregates them with an executive summary.
"""

__all__ = (
    "ArxivClient",
    "ArxivPaper",
    "ResearchFilter",
    "ResearchDigest",
    "DEFAULT_FILTERS",
)


from aria.research.arxiv_client import ArxivClient, ArxivPaper
from aria.research.filters import (
    ResearchFilter,
    DEFAULT_FILTERS,
)
from aria.research.digest import ResearchDigest
