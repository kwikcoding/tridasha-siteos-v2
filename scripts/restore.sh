#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into a NEW database (never over the live one by accident).
#
#   scripts/restore.sh backups/siteos-siteos-20261014-0900 --target siteos_restore [--media-dir backend/media-restore]
#
# Checks the .sha256 first, creates the target database (refuses if it already exists), restores into it and
# unpacks the files into --media-dir (default backend/media-restore). Point a backend at it with
#   DATABASE_URL=postgres://siteos:siteos@db:5432/siteos_restore MEDIA_ROOT=/app/media-restore
# Restoring over the main database is refused unless CONFIRM_REPLACE=<that database name> is set.
set -euo pipefail
base=${1:?backup path without extension}; shift
TARGET=""; MEDIA_DIR="backend/media-restore"; SERVICE=${DB_SERVICE:-db}; MAIN=${MAIN_DB:-siteos}
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET=$2; shift 2;;
    --media-dir) MEDIA_DIR=$2; shift 2;;
    *) echo "unknown option $1"; exit 2;;
  esac
done
[ -n "$TARGET" ] || { echo "--target <new database name> is required"; exit 2; }
[[ "$TARGET" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "target must be a plain database name"; exit 2; }
if [ "$TARGET" = "$MAIN" ] && [ "${CONFIRM_REPLACE:-}" != "$MAIN" ]; then
  echo "Refusing to restore over the main database '$MAIN'. Restore into a new name, check it, then switch."; exit 3
fi
( cd "$(dirname "$base")" && sha256sum -c "$(basename "$base").sha256" )
exists=$(docker compose exec -T "$SERVICE" psql -U siteos -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$TARGET'")
[ -z "$exists" ] || { echo "Database '$TARGET' already exists — choose another name."; exit 4; }
docker compose exec -T "$SERVICE" psql -U siteos -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $TARGET"
docker compose exec -T "$SERVICE" pg_restore -U siteos -d "$TARGET" --no-owner --no-privileges --exit-on-error < "$base.dump"
mkdir -p "$MEDIA_DIR"
tar -xzf "$base.media.tgz" -C "$MEDIA_DIR"
echo "Restored into database '$TARGET' and files into $MEDIA_DIR"
