from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import structlog

from aria.conjunction.core.types import SpaceObject
from aria.conjunction.data.maneuver_detect import ManeuverFlag, detect_maneuver

logger = structlog.get_logger()


DEFAULT_BASELINE_PATH = Path("data/runtime/cross_source_delta/baseline.json")


@dataclass(frozen=True)
class SourceSnapshot:
    source: str
    fetched_at: datetime
    objects_by_norad_id: dict[str, SpaceObject]

    @property
    def norad_ids(self) -> set[str]:
        return set(self.objects_by_norad_id.keys())


@dataclass(frozen=True)
class SourceDisagreement:
    norad_id: str
    name: str
    sources_present: tuple[str, ...]
    sources_absent: tuple[str, ...]


@dataclass(frozen=True)
class CrossSourceDelta:
    timestamp_iso: str
    sources: tuple[str, ...]
    n_objects_per_source: dict[str, int]
    new_objects: tuple[SpaceObject, ...] = ()
    missing_objects: tuple[str, ...] = ()
    source_disagreements: tuple[SourceDisagreement, ...] = ()
    maneuver_flags: tuple[ManeuverFlag, ...] = ()
    baseline_compared: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp_iso,
            "sources": list(self.sources),
            "n_objects_per_source": dict(self.n_objects_per_source),
            "new_objects": [
                {"norad_id": obj.norad_id, "name": obj.name}
                for obj in self.new_objects
            ],
            "missing_objects": list(self.missing_objects),
            "source_disagreements": [
                {
                    "norad_id": dis.norad_id,
                    "name": dis.name,
                    "sources_present": list(dis.sources_present),
                    "sources_absent": list(dis.sources_absent),
                }
                for dis in self.source_disagreements
            ],
            "maneuver_flags": [
                {
                    "norad_id": flag.norad_id,
                    "name": flag.name,
                    "detected_at": flag.detected_at.isoformat(),
                    "delta_mean_motion": flag.delta_mean_motion,
                    "delta_raan_deg": flag.delta_raan_deg,
                    "delta_eccentricity": flag.delta_eccentricity,
                    "confidence": flag.confidence,
                    "reason": flag.reason,
                }
                for flag in self.maneuver_flags
            ],
            "baseline_compared": self.baseline_compared,
        }


@dataclass
class _Baseline:
    snapshots: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def union_norad_ids(self) -> set[str]:
        union: set[str] = set()
        for source_data in self.snapshots.values():
            union.update(source_data.keys())
        return union

    def per_source_ids(self, source: str) -> set[str]:
        return set(self.snapshots.get(source, {}).keys())


class CrossSourceDeltaDetector:
    def __init__(
        self,
        *,
        baseline_path: Path = DEFAULT_BASELINE_PATH,
    ) -> None:
        self._baseline_path = baseline_path

    @property
    def baseline_path(self) -> Path:
        return self._baseline_path

    def load_baseline(self) -> _Baseline:
        if not self._baseline_path.exists():
            return _Baseline()
        try:
            payload = json.loads(self._baseline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "aria.cross_source_delta.baseline_load_failed",
                path=str(self._baseline_path), error=str(exc),
            )
            return _Baseline()
        snapshots = {}
        for source, items in (payload.get("snapshots") or {}).items():
            if not isinstance(items, dict):
                continue
            snapshots[source] = {
                str(norad_id): item for norad_id, item in items.items()
                if isinstance(item, dict)
            }
        return _Baseline(snapshots=snapshots)

    def write_baseline(self, snapshots: Iterable[SourceSnapshot]) -> None:
        self._baseline_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "written_at": datetime.now(tz=timezone.utc).isoformat(),
            "snapshots": {},
        }
        for snapshot in snapshots:
            payload["snapshots"][snapshot.source] = {
                norad_id: {
                    "name": obj.name,
                    "tle_line1": obj.tle_line1,
                    "tle_line2": obj.tle_line2,
                }
                for norad_id, obj in snapshot.objects_by_norad_id.items()
            }
        self._baseline_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8",
        )
        logger.info(
            "aria.cross_source_delta.baseline_written",
            path=str(self._baseline_path),
            sources=list(payload["snapshots"].keys()),
        )

    def compute(
        self,
        snapshots: list[SourceSnapshot],
        *,
        baseline: Optional[_Baseline] = None,
    ) -> CrossSourceDelta:
        if not snapshots:
            raise ValueError("at least one snapshot is required")
        baseline = baseline if baseline is not None else self.load_baseline()
        baseline_compared = bool(baseline.snapshots)

        union_ids: set[str] = set()
        for snapshot in snapshots:
            union_ids.update(snapshot.norad_ids)

        baseline_union = baseline.union_norad_ids()
        new_ids = union_ids - baseline_union if baseline_compared else set()
        missing_ids = baseline_union - union_ids if baseline_compared else set()

        new_objects: list[SpaceObject] = []
        seen_new: set[str] = set()
        for snapshot in snapshots:
            for norad_id in new_ids:
                if norad_id in seen_new:
                    continue
                obj = snapshot.objects_by_norad_id.get(norad_id)
                if obj is not None:
                    new_objects.append(obj)
                    seen_new.add(norad_id)

        disagreements: list[SourceDisagreement] = []
        all_sources = tuple(snapshot.source for snapshot in snapshots)
        if len(snapshots) >= 2:
            for norad_id in union_ids:
                present: list[str] = []
                absent: list[str] = []
                name = ""
                for snapshot in snapshots:
                    if norad_id in snapshot.objects_by_norad_id:
                        present.append(snapshot.source)
                        name = name or snapshot.objects_by_norad_id[norad_id].name
                    else:
                        absent.append(snapshot.source)
                if absent and present:
                    disagreements.append(
                        SourceDisagreement(
                            norad_id=norad_id,
                            name=name,
                            sources_present=tuple(present),
                            sources_absent=tuple(absent),
                        )
                    )

        maneuver_flags: list[ManeuverFlag] = []
        if baseline_compared:
            for snapshot in snapshots:
                baseline_for_source = baseline.snapshots.get(snapshot.source, {})
                if not baseline_for_source:
                    continue
                from aria.conjunction.data.tle_parser import (
                    TLEParseError,
                    TLEParser,
                )
                for norad_id, current_obj in snapshot.objects_by_norad_id.items():
                    baseline_entry = baseline_for_source.get(norad_id)
                    if not baseline_entry:
                        continue
                    line1 = baseline_entry.get("tle_line1")
                    line2 = baseline_entry.get("tle_line2")
                    name = baseline_entry.get("name") or current_obj.name
                    if not line1 or not line2:
                        continue
                    try:
                        prior_obj = TLEParser.parse_tle(line1, line2, name=name)
                    except TLEParseError:
                        continue
                    flag = detect_maneuver(prior_obj, current_obj)
                    if flag is not None:
                        maneuver_flags.append(flag)

        timestamp_iso = datetime.now(tz=timezone.utc).isoformat()
        n_per_source = {
            snapshot.source: len(snapshot.objects_by_norad_id)
            for snapshot in snapshots
        }
        return CrossSourceDelta(
            timestamp_iso=timestamp_iso,
            sources=all_sources,
            n_objects_per_source=n_per_source,
            new_objects=tuple(new_objects),
            missing_objects=tuple(sorted(missing_ids)),
            source_disagreements=tuple(disagreements),
            maneuver_flags=tuple(maneuver_flags),
            baseline_compared=baseline_compared,
        )


def format_delta_human(delta: CrossSourceDelta) -> str:
    lines: list[str] = []
    lines.append(f"Cross-source catalogue delta — {delta.timestamp_iso}")
    lines.append("")
    lines.append(f"Sources scanned ({len(delta.sources)}): " + ", ".join(delta.sources))
    for source, count in sorted(delta.n_objects_per_source.items()):
        lines.append(f"  {source:20s} {count:6d} objects")
    lines.append("")
    if not delta.baseline_compared:
        lines.append("(first run — no baseline comparison)")
    else:
        lines.append(f"NEW objects: {len(delta.new_objects)}")
        for obj in delta.new_objects[:25]:
            lines.append(f"  + {obj.norad_id:8s} {obj.name}")
        if len(delta.new_objects) > 25:
            lines.append(f"  ... and {len(delta.new_objects) - 25} more")
        lines.append("")
        lines.append(f"MISSING objects: {len(delta.missing_objects)}")
        for norad_id in delta.missing_objects[:25]:
            lines.append(f"  - {norad_id}")
        if len(delta.missing_objects) > 25:
            lines.append(f"  ... and {len(delta.missing_objects) - 25} more")
        lines.append("")
        lines.append(f"MANEUVERING objects: {len(delta.maneuver_flags)}")
        for flag in delta.maneuver_flags[:25]:
            lines.append(
                f"  ~ {flag.norad_id:8s} {flag.name} "
                f"(Δn={flag.delta_mean_motion:+.4f} rev/d, "
                f"ΔΩ={flag.delta_raan_deg:+.3f}°, "
                f"Δe={flag.delta_eccentricity:+.5f}, "
                f"conf={flag.confidence})"
            )
        if len(delta.maneuver_flags) > 25:
            lines.append(f"  ... and {len(delta.maneuver_flags) - 25} more")
    lines.append("")
    lines.append(f"SOURCE-DISAGREEMENT objects: {len(delta.source_disagreements)}")
    for dis in delta.source_disagreements[:25]:
        present = "+".join(dis.sources_present)
        absent = "+".join(dis.sources_absent)
        lines.append(
            f"  {dis.norad_id:8s} {dis.name:25s} present={present} absent={absent}"
        )
    if len(delta.source_disagreements) > 25:
        lines.append(f"  ... and {len(delta.source_disagreements) - 25} more")
    return "\n".join(lines)


def parse_celestrak_response_to_snapshot(
    *, source: str, raw_text: str, fetched_at: Optional[datetime] = None,
) -> SourceSnapshot:
    from aria.conjunction.data.tle_parser import TLEParser
    objects = TLEParser.parse_multi_tle(raw_text)
    return SourceSnapshot(
        source=source,
        fetched_at=fetched_at or datetime.now(tz=timezone.utc),
        objects_by_norad_id={obj.norad_id: obj for obj in objects},
    )
