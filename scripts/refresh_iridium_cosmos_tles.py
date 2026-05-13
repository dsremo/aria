"""R45 — refresh Iridium-Cosmos replay TLEs from SpaceTrack.

Pulls the actual 18-SDS broadcast TLEs for Iridium-33 (NORAD 24946)
and Cosmos-2251 (NORAD 22675) from Feb 9 2009 and writes them into
`src/aria/validation/data/iridium33_cosmos2251_2009.toml`.

After running, re-run `python -m aria.validation.iridium_cosmos_replay`
— the TLE-driven replay (Part A) should now produce a miss distance
within ~150 m of the historical 584 m.

Requirements:
  * SPACETRACK_USERNAME + SPACETRACK_PASSWORD env vars set
    (see `~/Music/DB_CREDENTIALS.md` + `aria-core/.env`).
  * `requests` Python package.
  * SpaceTrack account with civil-research access already approved.

Usage:
  python scripts/refresh_iridium_cosmos_tles.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    # Load the .env if dotenv is around — graceful fallback.
    try:
        from dotenv import load_dotenv
        load_dotenv(repo_root() / ".env")
    except ImportError:
        # Manual fallback.
        env_path = repo_root() / ".env"
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    if not os.environ.get("SPACETRACK_USERNAME"):
        print("[refresh_iridium_cosmos_tles] SPACETRACK_USERNAME not set",
              file=sys.stderr)
        return 1

    from aria.conjunction.data.spacetrack_session import (
        fetch_iridium_cosmos_2009,
    )

    out_path = (
        repo_root()
        / "src" / "aria" / "validation" / "data"
        / "iridium33_cosmos2251_2009.toml"
    )
    print(f"[refresh_iridium_cosmos_tles] writing → {out_path}")
    try:
        result = fetch_iridium_cosmos_2009(out_path=str(out_path))
    except Exception as exc:
        print(f"[refresh_iridium_cosmos_tles] failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"  Iridium-33 epoch: {result.get('primary_epoch')}\n"
        f"  Cosmos-2251 epoch: {result.get('secondary_epoch')}\n"
        f"  Re-run `python -m aria.validation.iridium_cosmos_replay` to verify."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
