from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


ISS_PUBLISHED_AVG_LOAD_KW = 84.0
ISS_PUBLISHED_PEAK_GENERATION_KW = 240.0
ISS_PUBLISHED_NOMINAL_GENERATION_KW = 95.0
ISS_PUBLISHED_BATTERY_TOTAL_KWH = 224.0
ISS_PUBLISHED_BUS_NOMINAL_V = 160.0
ISS_PUBLISHED_ECLIPSE_FRACTION = 0.36

ISS_PUBLISHED_CITATIONS = (
    "ISS Electrical Power System Specification SSP 30482",
    "Mike Suffredini, ISS Program Manager 2014 testimony — 84 kW avg load",
    "Loff, S. (2017) NASA Spaceflight ISS Power Roll-out Solar Array overview",
    "Steel, B. (2019) ISS Battery Replacement and Augmentation",
)


@dataclass(frozen=True)
class ValidationDelta:
    parameter: str
    measured_value: float
    published_value: float
    relative_error: float
    within_tolerance: bool
    units: str = ""

    @property
    def relative_error_pct(self) -> float:
        return self.relative_error * 100.0


@dataclass(frozen=True)
class IssValidationReport:
    deltas: tuple[ValidationDelta, ...]
    overall_within_tolerance: bool
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "overall_within_tolerance": self.overall_within_tolerance,
            "notes": self.notes,
            "deltas": [
                {
                    "parameter": delta.parameter,
                    "measured": delta.measured_value,
                    "published": delta.published_value,
                    "relative_error_pct": round(delta.relative_error_pct, 2),
                    "within_tolerance": delta.within_tolerance,
                    "units": delta.units,
                }
                for delta in self.deltas
            ],
        }


def _compare(
    measured: float,
    published: float,
    tolerance: float,
    parameter: str,
    units: str = "",
) -> ValidationDelta:
    if published == 0:
        relative_error = float("inf") if measured != 0 else 0.0
    else:
        relative_error = abs(measured - published) / abs(published)
    return ValidationDelta(
        parameter=parameter,
        measured_value=measured,
        published_value=published,
        relative_error=relative_error,
        within_tolerance=relative_error <= tolerance,
        units=units,
    )


def validate_against_iss_published_numbers(
    *,
    measured_avg_generation_kw: float,
    measured_peak_generation_kw: float,
    measured_battery_total_kwh: float,
    measured_eclipse_fraction: float,
    tolerance_pct: float = 25.0,
) -> IssValidationReport:
    tolerance = tolerance_pct / 100.0
    deltas = (
        _compare(
            measured_avg_generation_kw, ISS_PUBLISHED_NOMINAL_GENERATION_KW,
            tolerance, "avg_generation", "kW",
        ),
        _compare(
            measured_peak_generation_kw, ISS_PUBLISHED_PEAK_GENERATION_KW,
            tolerance, "peak_generation", "kW",
        ),
        _compare(
            measured_battery_total_kwh, ISS_PUBLISHED_BATTERY_TOTAL_KWH,
            tolerance, "battery_total_capacity", "kWh",
        ),
        _compare(
            measured_eclipse_fraction, ISS_PUBLISHED_ECLIPSE_FRACTION,
            0.10, "eclipse_fraction", "fraction",
        ),
    )
    overall = all(delta.within_tolerance for delta in deltas)
    notes = (
        "Tolerance band is intentionally loose (±25% on power, ±10% on "
        "eclipse fraction): the ISS array configuration and degradation "
        "state varies; this is a sanity-check against published "
        "averages, not a precision validation. Citations: "
        + "; ".join(ISS_PUBLISHED_CITATIONS)
    )
    return IssValidationReport(
        deltas=deltas, overall_within_tolerance=overall, notes=notes,
    )
