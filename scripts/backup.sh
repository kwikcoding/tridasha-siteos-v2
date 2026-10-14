#!/usr/bin/env bash
# Back up the SiteOS database and uploaded files.
#
#   scripts/backup.sh [out_dir]                    # main stack (service "db", database "siteos", backend/media)
#   DB_SERVICE=db-demo DB_NAME=siteos_demo MEDIA_DIR=backend/media-demo scripts/backup.sh   # demo stack
#
# Writes <out_dir>/siteos-<timestamp>.dump (pg_dump custom format), .media.tgz and .sha256.
# Read-only for the database: it never changes or locks out the running app.
set -euo pipefail
OUT=${1:-backups}
SERVICE=${DB_SERVICE:-db}
DB=${DB_NAME:-siteos}
MEDIA=${MEDIA_DIR:-backend/media}
mkdir -p "$OUT"
base="$OUT/siteos-${DB}-$(date +%Y%m%d-%H%M%S)"

docker compose exec -T "$SERVICE" pg_dump -U siteos -d "$DB" -Fc --no-owner --no-privileges > "$base.dump"
# the dump must be readable before we call it a backup
docker compose exec -T "$SERVICE" pg_restore --list < "$base.dump" > /dev/null
if [ -d "$MEDIA" ]; then tar -czf "$base.media.tgz" -C "$MEDIA" .; else tar -czf "$base.media.tgz" --files-from /dev/null; fi
( cd "$OUT" && sha256sum "$(basename "$base").dump" "$(basename "$base").media.tgz" > "$(basename "$base").sha256" )
echo "Backup written: $base.{dump,media.tgz,sha256} ($(du -h "$base.dump" | cut -f1) database)"
echo "$base"
