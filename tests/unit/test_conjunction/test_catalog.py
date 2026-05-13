"""Tests for SpaceObjectCatalog (in-memory + SQLite persistence)."""

import math
from datetime import datetime, timedelta

from aria.conjunction.core.types import ObjectType, OrbitalElements, SpaceObject
from aria.conjunction.data.catalog import SpaceObjectCatalog
from aria.conjunction.data.tle_parser import TLEParser

# ISS TLE (valid checksums)
ISS_LINE1 = "1 25544U 98067A   26090.13309952  .00011434  00000+0  21777-3 0  9998"
ISS_LINE2 = "2 25544  51.6341 326.3497 0006203 253.7499 106.2807 15.48671303559658"

# POISK TLE (valid checksums)
HST_LINE1 = "1 36086U 09060A   26090.13309952  .00011434  00000+0  21777-3 0  9996"
HST_LINE2 = "2 36086  51.6341 326.3497 0006203 253.7499 106.2807 15.48671303559459"
HST_NORAD = "36086"


def _make_obj(norad_id: str, sma: float = 7000.0, age_hours: float = 0.0) -> SpaceObject:
    epoch = datetime.utcnow() - timedelta(hours=age_hours)
    elements = OrbitalElements(
        semi_major_axis=sma,
        eccentricity=0.001,
        inclination=math.radians(51.6),
        raan=0.0,
        arg_perigee=0.0,
        true_anomaly=0.0,
        epoch=epoch,
    )
    return SpaceObject(
        norad_id=norad_id,
        name=f"OBJ-{norad_id}",
        tle_line1="1 00000U 00000A   00001.00000000  .00000000  00000-0  00000-0 0     0",
        tle_line2="2 00000  51.6000   0.0000 0001000   0.0000   0.0000 15.00000000     0",
        object_type=ObjectType.PAYLOAD,
        elements=elements,
    )


# ---------------------------------------------------------------------------
# In-memory catalog
# ---------------------------------------------------------------------------

class TestSpaceObjectCatalogInMemory:

    def test_empty_catalog(self):
        cat = SpaceObjectCatalog()
        assert len(cat) == 0
        assert cat.size == 0

    def test_add_and_get(self):
        cat = SpaceObjectCatalog()
        obj = _make_obj("25544")
        cat.add(obj)
        assert cat.get("25544") is obj

    def test_get_missing_returns_none(self):
        cat = SpaceObjectCatalog()
        assert cat.get("00001") is None

    def test_add_overwrite(self):
        cat = SpaceObjectCatalog()
        obj1 = _make_obj("25544", sma=7000.0)
        obj2 = _make_obj("25544", sma=7100.0)
        cat.add(obj1)
        cat.add(obj2)
        assert cat.get("25544").elements.semi_major_axis == 7100.0
        assert len(cat) == 1

    def test_contains(self):
        cat = SpaceObjectCatalog()
        obj = _make_obj("25544")
        cat.add(obj)
        assert "25544" in cat
        assert "99999" not in cat

    def test_remove(self):
        cat = SpaceObjectCatalog()
        obj = _make_obj("25544")
        cat.add(obj)
        cat.remove("25544")
        assert cat.get("25544") is None
        assert len(cat) == 0

    def test_remove_nonexistent_no_error(self):
        cat = SpaceObjectCatalog()
        cat.remove("99999")  # Should not raise

    def test_all_objects(self):
        cat = SpaceObjectCatalog()
        for i in range(5):
            cat.add(_make_obj(str(i)))
        objs = cat.all_objects()
        assert len(objs) == 5
        assert all(isinstance(o, SpaceObject) for o in objs)

    def test_add_many(self):
        cat = SpaceObjectCatalog()
        objs = [_make_obj(str(i)) for i in range(10)]
        cat.add_many(objs)
        assert len(cat) == 10

    def test_add_many_empty(self):
        cat = SpaceObjectCatalog()
        cat.add_many([])
        assert len(cat) == 0

    def test_stale_objects_none_when_fresh(self):
        cat = SpaceObjectCatalog()
        cat.add(_make_obj("1", age_hours=0.0))  # fresh TLE
        stale = cat.stale_objects(max_age_hours=48.0)
        assert len(stale) == 0

    def test_stale_objects_detected(self):
        cat = SpaceObjectCatalog()
        cat.add(_make_obj("1", age_hours=72.0))  # 72h old
        stale = cat.stale_objects(max_age_hours=48.0)
        assert len(stale) == 1

    def test_stale_objects_mixed(self):
        cat = SpaceObjectCatalog()
        cat.add(_make_obj("1", age_hours=10.0))   # fresh
        cat.add(_make_obj("2", age_hours=100.0))  # stale
        cat.add(_make_obj("3", age_hours=50.0))   # stale
        stale = cat.stale_objects(max_age_hours=48.0)
        assert len(stale) == 2

    def test_stale_objects_no_elements(self):
        """Objects without elements should not be flagged as stale."""
        cat = SpaceObjectCatalog()
        obj_no_el = SpaceObject(
            norad_id="00001", name="X", tle_line1="", tle_line2="",
            elements=None,
        )
        cat.add(obj_no_el)
        stale = cat.stale_objects(max_age_hours=0.0)
        assert len(stale) == 0

    def test_load_tle_file(self, tmp_path):
        tle_content = f"ISS (ZARYA)\n{ISS_LINE1}\n{ISS_LINE2}\n"
        tle_file = tmp_path / "test.tle"
        tle_file.write_text(tle_content)

        cat = SpaceObjectCatalog()
        count = cat.load_tle_file(tle_file)
        assert count == 1
        assert "25544" in cat

    def test_load_tle_file_multiple(self, tmp_path):
        tle_content = (
            f"ISS (ZARYA)\n{ISS_LINE1}\n{ISS_LINE2}\n"
            f"POISK\n{HST_LINE1}\n{HST_LINE2}\n"
        )
        tle_file = tmp_path / "multi.tle"
        tle_file.write_text(tle_content)

        cat = SpaceObjectCatalog()
        count = cat.load_tle_file(tle_file)
        assert count == 2
        assert "25544" in cat
        assert HST_NORAD in cat


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------

class TestSpaceObjectCatalogSQLite:

    def test_sqlite_add_and_reload(self, tmp_path):
        db_path = tmp_path / "catalog.db"

        # Create catalog and add object
        cat1 = SpaceObjectCatalog(db_path=db_path)
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        cat1.add(iss)

        # Reload from same DB
        cat2 = SpaceObjectCatalog(db_path=db_path)
        assert "25544" in cat2
        assert cat2.get("25544").name == "ISS"

    def test_sqlite_remove_persists(self, tmp_path):
        db_path = tmp_path / "catalog.db"

        cat1 = SpaceObjectCatalog(db_path=db_path)
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        cat1.add(iss)
        cat1.remove("25544")

        # Reload — should be gone
        cat2 = SpaceObjectCatalog(db_path=db_path)
        assert "25544" not in cat2

    def test_sqlite_add_many_persists(self, tmp_path):
        db_path = tmp_path / "catalog.db"

        cat1 = SpaceObjectCatalog(db_path=db_path)
        iss = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS")
        hst = TLEParser.parse_tle(HST_LINE1, HST_LINE2, name="POISK")
        cat1.add_many([iss, hst])

        cat2 = SpaceObjectCatalog(db_path=db_path)
        assert len(cat2) == 2

    def test_sqlite_upsert(self, tmp_path):
        """Adding the same NORAD ID twice should update, not duplicate."""
        db_path = tmp_path / "catalog.db"

        cat1 = SpaceObjectCatalog(db_path=db_path)
        iss1 = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS-V1")
        iss2 = TLEParser.parse_tle(ISS_LINE1, ISS_LINE2, name="ISS-V2")
        cat1.add(iss1)
        cat1.add(iss2)

        cat2 = SpaceObjectCatalog(db_path=db_path)
        assert len(cat2) == 1
        assert cat2.get("25544").name == "ISS-V2"
