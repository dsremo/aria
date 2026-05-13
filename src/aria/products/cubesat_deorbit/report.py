"""1-page PDF / HTML report for a de-orbit recommendation.

ReportLab is the canonical Python PDF generator but it is a heavy
dependency.  To keep the dependency footprint small we generate the
report as printable HTML by default and convert it to PDF using
``weasyprint`` when available.  HTML alone is sufficient for a sales
demo and for sharing in a browser.

The function is dependency-tolerant: if neither library is
installed, :func:`render_report` returns the HTML string and a flag
telling the caller PDF rendering was skipped.
"""

from __future__ import annotations

import html
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from aria.products.cubesat_deorbit.advisor import (
    DeOrbitRecommendation,
    Decision,
)


_REPORT_CSS = """
:root { --accent:#003366; --grey:#666; --pass:#1f7a3a; --fail:#a8232c; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color:#222; margin: 32px 36px; line-height: 1.4; }
h1 { color: var(--accent); margin: 0 0 4px 0; font-size: 22px; }
h2 { color: var(--accent); font-size: 14px; margin: 18px 0 8px 0; border-bottom:1px solid #ddd; padding-bottom:2px; }
.subtitle { color: var(--grey); margin: 0 0 16px 0; font-size: 12px; }
.decision { display:inline-block; padding:6px 14px; border-radius:4px;
            color:white; font-weight:600; font-size:14px; margin: 12px 0; }
.decision.natural_decay { background: var(--pass); }
.decision.burn_required { background: #b27200; }
.decision.burn_optional { background: #b27200; }
.decision.infeasible    { background: var(--fail); }
.kv { display:grid; grid-template-columns: 240px 1fr; row-gap: 6px; column-gap: 12px; font-size: 13px; }
.kv .k { color: var(--grey); }
.kv .v { color: #111; }
.pass { color: var(--pass); font-weight: 600; }
.fail { color: var(--fail); font-weight: 600; }
ul { padding-left: 18px; margin: 4px 0; font-size: 13px; }
.footer { margin-top: 28px; color: var(--grey); font-size: 10px;
          border-top: 1px solid #ddd; padding-top: 8px; }
.tier { display:inline-block; background:#eef; color:#225; padding:2px 8px;
        border-radius:3px; font-size:11px; }
"""


def _esc(x) -> str:
    return html.escape(str(x))


def _decision_class(d: Decision) -> str:
    return d.value


def _yesno(v: bool) -> str:
    return ('<span class="pass">PASS</span>' if v
            else '<span class="fail">FAIL</span>')


def render_html(rec: DeOrbitRecommendation, mission_name: str = "CubeSat") -> str:
    """Render the recommendation as a self-contained HTML document."""
    burn_html = ""
    if rec.burn_plan is not None:
        b = rec.burn_plan
        burn_html = f"""
<h2>Propulsive de-orbit plan</h2>
<div class="kv">
  <div class="k">Δv required</div><div class="v">{b.delta_v_mps:.2f} m/s</div>
  <div class="k">Direction</div><div class="v">{_esc(b.direction)}</div>
  <div class="k">Propellant burn</div><div class="v">{b.propellant_kg_burned:.3f} kg
      (margin {b.propellant_margin_kg:.3f} kg)</div>
  <div class="k">Target periapsis</div><div class="v">{b.target_periapsis_km:.0f} km</div>
  <div class="k">Burn epoch (UTC)</div><div class="v">{_esc(b.burn_epoch_utc.isoformat())}</div>
  <div class="k">Expected reentry (UTC)</div><div class="v">{_esc(b.expected_reentry_utc.isoformat())}</div>
</div>"""

    fp_html = ""
    if rec.footprint is not None:
        f = rec.footprint
        fp_html = f"""
<h2>Re-entry footprint</h2>
<div class="kv">
  <div class="k">Nominal lat / lon</div><div class="v">
      {f.nominal_lat_deg:.1f}° / {f.nominal_lon_deg:.1f}°</div>
  <div class="k">Along-track 3σ</div><div class="v">{f.along_track_3sigma_km:.0f} km</div>
  <div class="k">Cross-track 3σ</div><div class="v">{f.cross_track_3sigma_km:.0f} km</div>
  <div class="k">Casualty area est.</div><div class="v">{f.casualty_area_m2:.1f} m²</div>
  <div class="k">Over water (heur.)</div><div class="v">
      {'yes' if f.occurs_over_water else 'no'}</div>
</div>"""

    actions = "".join(f"<li>{_esc(a)}</li>" for a in rec.operator_actions)
    rationale = "".join(f"<li>{_esc(r)}</li>" for r in rec.rationale)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>ARIA De-Orbit Recommendation — {_esc(mission_name)}</title>
<style>{_REPORT_CSS}</style>
</head><body>
<h1>ARIA CubeSat End-of-Life Advisor</h1>
<p class="subtitle">Mission: {_esc(mission_name)} ·
   Generated: {_esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}
   · <span class="tier">Tier-{_esc(rec.confidence_tier)}</span></p>

<div class="decision {_decision_class(rec.decision)}">{_esc(rec.decision.value.replace("_", " ").upper())}</div>

<h2>Natural-decay analysis</h2>
<div class="kv">
  <div class="k">Lifetime (years)</div><div class="v">{rec.natural_decay.lifetime_years:.2f}</div>
  <div class="k">Lifetime (days)</div><div class="v">{rec.natural_decay.lifetime_days:.0f}</div>
  <div class="k">FCC 5-yr disposal</div><div class="v">{_yesno(rec.compliance.fcc_5_year)}
      <span style="color:#888"> (margin {rec.compliance.fcc_5_year_margin_days:+.0f} d)</span></div>
  <div class="k">NASA 25-yr ODMSP</div><div class="v">{_yesno(rec.compliance.nasa_25_year)}
      <span style="color:#888"> (margin {rec.compliance.nasa_25_year_margin_days:+.0f} d)</span></div>
</div>
{burn_html}
{fp_html}
<h2>Rationale</h2>
<ul>{rationale}</ul>
<h2>Operator actions</h2>
<ul>{actions}</ul>

<div class="footer">
This is a Tier-{_esc(rec.confidence_tier)}-confidence recommendation per
docs/UNCERTAINTY.md.  King-Hele decay carries factor-2 uncertainty in low solar
activity; reentry footprint is bounded above by 200 km × 30 km 3σ pending a
high-fidelity break-up model.  Operator is responsible for FAA AST + ITU
notification and for confirming actual debris-mitigation compliance with the
licensing authority.
</div>
</body></html>
"""


def render_report(
    rec: DeOrbitRecommendation,
    output_path: Path | str,
    mission_name: str = "CubeSat",
) -> Tuple[Path, bool]:
    """Render the recommendation to ``output_path``.

    If ``output_path`` ends in ``.pdf`` and ``weasyprint`` is
    importable, a PDF is produced; otherwise the file is written as
    HTML.  Returns ``(path_written, is_pdf)``.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    htmltext = render_html(rec, mission_name=mission_name)
    if output_path.suffix.lower() == ".pdf":
        try:
            from weasyprint import HTML
            HTML(string=htmltext).write_pdf(str(output_path))
            return output_path, True
        except Exception:
            html_alt = output_path.with_suffix(".html")
            html_alt.write_text(htmltext, encoding="utf-8")
            return html_alt, False
    output_path.write_text(htmltext, encoding="utf-8")
    return output_path, False
