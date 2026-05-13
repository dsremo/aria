"""Application configuration via Dynaconf."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dynaconf import Dynaconf

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CONFIGS_DIR = _PROJECT_ROOT / "configs"


@lru_cache(maxsize=1)
def get_settings() -> Dynaconf:
    """Return the singleton Dynaconf settings object."""
    return Dynaconf(
        envvar_prefix="GENASTRA",
        settings_files=[
            str(_CONFIGS_DIR / "default.yaml"),
            str(_CONFIGS_DIR / "production.yaml"),
            str(_CONFIGS_DIR / "testing.yaml"),
        ],
        environments=True,
        env_switcher="GENASTRA_ENV",
        load_dotenv=True,
    )


# Convenience aliases
settings = get_settings()
