"""Parse HYG-Database v3 (Hipparcos + Yale + Gliese, by David Nash).

The HYG v3 catalog is the standard merged stellar database used by
amateur astronomy software (Stellarium, Celestia). 119,614 entries,
stars to V≈12, plus the Sun. Public-domain (CC0).

We compact it to a JSON list of {ra,dec,mag,bv,pmra,pmdec,name,id}
and apply a magnitude filter (default V≤9.0, ~84k stars) so the
shipped file stays reasonable. Field meanings:

- ra:    right ascension at J2000 [deg]    (HYG stores it in *hours*)
- dec:   declination at J2000   [deg]
- mag:   apparent V magnitude
- bv:    B-V color index
- pmra:  proper motion in RA  [mas/yr]
- pmdec: proper motion in Dec [mas/yr]
- name:  HYG "proper" or Bayer/Flamsteed designation (may be empty)
- id:    HYG internal ID

Run:
    python scripts/parse_hyg.py /tmp/hyg_v3.csv \\
        src/aria/simulation/_data/hyg.json --mag-cap 9.0
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def main(src: Path, dst: Path, mag_cap: float) -> None:
    out: List[Dict[str, Any]] = []
    skipped = 0
    with src.open() as fh:
        rdr = csv.DictReader(fh)
        for row in rdr:
            try:
                mag = float(row["mag"])
            except (ValueError, KeyError):
                skipped += 1
                continue
            if mag > mag_cap:
                continue
            try:
                ra_h = float(row["ra"])      # hours
                dec_d = float(row["dec"])    # degrees
            except (ValueError, KeyError):
                skipped += 1
                continue
            try:
                bv = float(row["ci"]) if row["ci"] else 0.0
            except ValueError:
                bv = 0.0
            try:
                pmra = float(row["pmra"]) if row["pmra"] else 0.0
                pmdec = float(row["pmdec"]) if row["pmdec"] else 0.0
            except ValueError:
                pmra = pmdec = 0.0

            name = (row.get("proper") or "").strip()
            if not name:
                bf = (row.get("bf") or "").strip()
                if bf:
                    name = bf

            try:
                hip = int(row["hip"]) if row.get("hip") else 0
            except ValueError:
                hip = 0
            out.append({
                "id": int(row["id"]),
                "hip": hip,
                "ra": round(ra_h * 15.0, 5),
                "dec": round(dec_d, 5),
                "mag": round(mag, 2),
                "bv": round(bv, 3),
                "pmra": round(pmra, 1),
                "pmdec": round(pmdec, 1),
                "name": name,
            })

    out.sort(key=lambda r: r["mag"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w") as fh:
        json.dump(out, fh, separators=(",", ":"))

    sz = dst.stat().st_size / 1024
    unit = "KB" if sz < 1024 else "MB"
    if unit == "MB":
        sz /= 1024
    print(f"parsed: {len(out):>7} stars (V≤{mag_cap})  skipped: {skipped}  "
          f"out: {dst}  size: {sz:.1f} {unit}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("src", type=Path, nargs="?", default=Path("/tmp/hyg_v3.csv"))
    p.add_argument("dst", type=Path, nargs="?",
                   default=Path("src/aria/simulation/_data/hyg.json"))
    p.add_argument("--mag-cap", type=float, default=9.0,
                   help="Maximum V magnitude to include (default 9.0)")
    args = p.parse_args()
    main(args.src, args.dst, args.mag_cap)
