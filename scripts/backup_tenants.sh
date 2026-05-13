#!/usr/bin/env bash
# Nightly backup of the screener's SQLite tenant store.
#
# Configure once:
#
#   crontab -e
#     # ARIA tenant-store backup — 03:17 every day
#     17 3 * * * /opt/aria-core/scripts/backup_tenants.sh >> /var/log/aria-backup.log 2>&1
#
# Optionally set ARIA_BACKUP_S3_PATH=s3://bucket/prefix to off-site
# the backup with `aws s3 cp` (silently skipped if aws CLI absent).
#
# The script is idempotent and exits 0 even when nothing changed —
# crontab won't email you noise.

set -Eeuo pipefail

DB_PATH="${ARIA_SCREENER_DB:-/data/screener_tenants.sqlite3}"
BACKUP_DIR="${ARIA_BACKUP_DIR:-/var/backups/aria-screener}"
KEEP_LAST="${ARIA_BACKUP_KEEP:-30}"
S3_PATH="${ARIA_BACKUP_S3_PATH:-}"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
    echo "[$(date -u +%FT%TZ)] tenant DB not found at $DB_PATH — nothing to back up"
    exit 0
fi

stamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
target="$BACKUP_DIR/screener_tenants-$stamp.sqlite3"

# Use SQLite's online .backup so we don't have to stop the service.
sqlite3 "$DB_PATH" ".backup '$target'"

# Verify integrity of the copy
if ! sqlite3 "$target" "PRAGMA integrity_check;" | grep -qx "ok"; then
    echo "[$(date -u +%FT%TZ)] integrity check FAILED for $target" >&2
    rm -f "$target"
    exit 1
fi

# gzip to save space
gzip -9 "$target"
target="$target.gz"

# Optionally off-site
if [[ -n "$S3_PATH" ]] && command -v aws >/dev/null 2>&1 ; then
    aws s3 cp "$target" "$S3_PATH/" >/dev/null
fi

# Prune old backups beyond the keep window
ls -1t "$BACKUP_DIR"/screener_tenants-*.sqlite3.gz 2>/dev/null \
    | awk -v keep="$KEEP_LAST" 'NR > keep' \
    | xargs -r rm -f

bytes=$(stat -c '%s' "$target")
echo "[$(date -u +%FT%TZ)] backup ok: $target ($bytes bytes)"
