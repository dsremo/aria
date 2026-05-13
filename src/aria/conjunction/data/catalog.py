"""
Space object catalog management.

In-memory catalog with optional SQLite persistence for bulk TLE operations.
Tracks TLE age (epoch staleness) for data quality assessment.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from aria.conjunction.core.types import ObjectType, SpaceObject
from aria.conjunction.data.tle_parser import TLEParser


class SpaceObjectCatalog:
    """Manages a collection of tracked space objects.

    Primary storage is in-memory dict keyed by NORAD ID.
    Optional SQLite backend for persistence across sessions.
    """

    def __init__(self, db_path: str | Path | None = None):
        self._objects: dict[str, SpaceObject] = {}
        self._db_path = Path(db_path) if db_path else None

        if self._db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        """Initialize SQLite schema."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tle_catalog (
                    norad_id TEXT PRIMARY KEY,
                    name TEXT,
                    tle_line1 TEXT NOT NULL,
                    tle_line2 TEXT NOT NULL,
                    object_type TEXT DEFAULT 'UNKNOWN',
                    rcs_size TEXT DEFAULT 'MEDIUM',
                    radius_m REAL DEFAULT 1.0,
                    updated_at TEXT NOT NULL
                )
            """)

    def _load_from_db(self) -> None:
        """Load all objects from SQLite into memory."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT * FROM tle_catalog").fetchall()
            for row in rows:
                norad_id, name, line1, line2, obj_type, rcs, radius, _ = row
                try:
                    obj = TLEParser.parse_tle(
                        line1, line2,
                        name=name,
                        object_type=ObjectType(obj_type),
                    )
                    obj.rcs_size = rcs
                    obj.radius_m = radius
                    self._objects[norad_id] = obj
                except Exception:
                    continue

    def add(self, obj: SpaceObject) -> None:
        """Add or update a space object in the catalog."""
        self._objects[obj.norad_id] = obj

        if self._db_path:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO tle_catalog
                       (norad_id, name, tle_line1, tle_line2,
                        object_type, rcs_size, radius_m, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        obj.norad_id,
                        obj.name,
                        obj.tle_line1,
                        obj.tle_line2,
                        obj.object_type.value,
                        obj.rcs_size,
                        obj.radius_m,
                        datetime.utcnow().isoformat(),
                    ),
                )

    def add_many(self, objects: list[SpaceObject]) -> None:
        """Bulk add objects."""
        for obj in objects:
            self._objects[obj.norad_id] = obj

        if self._db_path:
            with sqlite3.connect(self._db_path) as conn:
                conn.executemany(
                    """INSERT OR REPLACE INTO tle_catalog
                       (norad_id, name, tle_line1, tle_line2,
                        object_type, rcs_size, radius_m, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            o.norad_id,
                            o.name,
                            o.tle_line1,
                            o.tle_line2,
                            o.object_type.value,
                            o.rcs_size,
                            o.radius_m,
                            datetime.utcnow().isoformat(),
                        )
                        for o in objects
                    ],
                )

    def get(self, norad_id: str) -> SpaceObject | None:
        """Retrieve an object by NORAD ID."""
        return self._objects.get(norad_id)

    def remove(self, norad_id: str) -> None:
        """Remove an object from the catalog."""
        self._objects.pop(norad_id, None)
        if self._db_path:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM tle_catalog WHERE norad_id = ?", (norad_id,))

    def all_objects(self) -> list[SpaceObject]:
        """Return all objects in the catalog."""
        return list(self._objects.values())

    def stale_objects(self, max_age_hours: float = 48.0) -> list[SpaceObject]:
        """Return objects whose TLE epoch is older than max_age_hours from now."""
        now = datetime.utcnow()
        cutoff = timedelta(hours=max_age_hours)
        stale = []
        for obj in self._objects.values():
            if obj.elements and (now - obj.elements.epoch) > cutoff:
                stale.append(obj)
        return stale

    def load_tle_file(self, filepath: str | Path) -> int:
        """Load TLEs from a file (3-line or 2-line format). Returns count loaded."""
        text = Path(filepath).read_text()
        objects = TLEParser.parse_multi_tle(text)
        self.add_many(objects)
        return len(objects)

    @property
    def size(self) -> int:
        return len(self._objects)

    def __len__(self) -> int:
        return self.size

    def __contains__(self, norad_id: str) -> bool:
        return norad_id in self._objects
