#!/usr/bin/env bash
# Nightly Postgres backup. Schedule via cron (see docs/deployment.md §5):
#   0 2 * * * BACKUP_DIR=/srv/school/backups DATABASE_URL=postgres://... scripts/backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/school/backups}"
DATABASE_URL="${DATABASE_URL:?DATABASE_URL must be set (postgres://user:pass@host:port/db)}"

mkdir -p "$BACKUP_DIR"
pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/school-$(date +%Y%m%d-%H%M).sql.gz"
find "$BACKUP_DIR" -name 'school-*.sql.gz' -mtime +30 -delete
