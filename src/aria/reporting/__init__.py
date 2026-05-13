"""ARIA Mission Reporting — post-mission report generation.

Generates structured text, JSON, and HTML reports from MissionResults,
DashboardSnapshot, and interstellar challenge states.
"""

from aria.reporting.mission_report import (
    MissionReportGenerator,
    MissionScore,
    ReportFormat,
)

__all__ = [
    "MissionReportGenerator",
    "MissionScore",
    "ReportFormat",
]
