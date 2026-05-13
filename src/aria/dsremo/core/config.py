"""Configuration management — layered: YAML → env vars → CLI overrides.

Uses dynaconf for environment-aware config with secret injection.
Config is loaded once at startup and passed explicitly (no global state).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from dynaconf import Dynaconf

logger = structlog.get_logger()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_CONFIG = _PROJECT_ROOT / "configs" / "dsremo.yaml"
_DOTENV_PATH = _PROJECT_ROOT / ".env"


def _load_dotenv() -> None:
    """Load .env file into os.environ. No-op if file doesn't exist."""
    if not _DOTENV_PATH.exists():
        return
    with open(_DOTENV_PATH) as f:
        import os
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Don't override existing env vars (explicit export takes priority)
            if key not in os.environ:
                os.environ[key] = value


def load_config(
    config_path: Path | None = None,
    env_prefix: str = "DSREMO",
) -> Dynaconf:
    """Load configuration with layered overrides.

    Priority (highest wins): env vars → config file → defaults.
    Secrets (passwords, keys) MUST come from env vars — they're never in YAML.
    """
    # Load .env into os.environ BEFORE dynaconf reads config.
    # This way DSREMO_DB_PASSWORD etc. are available everywhere.
    _load_dotenv()

    path = config_path or _DEFAULT_CONFIG

    if not path.exists():
        logger.warning("config_file_missing", path=str(path))

    settings = Dynaconf(
        settings_files=[str(path)],
        envvar_prefix=env_prefix,
        environments=False,
        load_dotenv=False,  # we already loaded it above
    )

    # Apply DSREMO_DB_* env vars to database.* config
    # (dynaconf's double-underscore convention would require DSREMO_DATABASE__HOST)
    _apply_env_overrides(settings)

    _validate_required(settings)
    logger.info("config_loaded", path=str(path))
    return settings


def _apply_env_overrides(settings: Dynaconf) -> None:
    """Map flat DSREMO_DB_* env vars onto nested database.* config keys."""
    import os

    env_map = {
        "DSREMO_DB_HOST": "database.host",
        "DSREMO_DB_PORT": "database.port",
        "DSREMO_DB_USER": "database.user",
        "DSREMO_DB_PASSWORD": "database.password",
        "DSREMO_DB_NAME": "database.name",
        "DSREMO_HMAC_SECRET": "security.hmac_secret",
        "DSREMO_WEBHOOK_URL": "alerts.webhook_url",
        "DSREMO_JWT_SECRET":  "auth.jwt_secret",
    }

    for env_var, config_key in env_map.items():
        val = os.environ.get(env_var)
        if val:
            settings.set(config_key, val)


def _validate_required(settings: Dynaconf) -> None:
    """Fail fast if critical config is missing."""
    warnings: list[str] = []

    db_password = settings.get("database.password", "")
    if not db_password:
        warnings.append("database.password not set — DB connection will fail")

    if warnings:
        for w in warnings:
            logger.warning("config_validation", issue=w)


def get_nested(settings: Dynaconf, key: str, default: Any = None) -> Any:
    """Safely get a nested config value like 'detection.z_score_threshold'."""
    try:
        return settings.get(key, default)
    except (KeyError, AttributeError):
        return default
