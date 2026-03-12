#!/usr/bin/env bash
# Automated PostgreSQL backup with rotation.
# Usage: backup.sh [BACKUP_DIR]
#
# Environment: PGHOST, PGUSER, PGPASSWORD, PGDATABASE (set by docker-compose)
set -euo pipefail

BACKUP_DIR="${1:-/backups}"
DAILY_KEEP=7
WEEKLY_KEEP=4
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK="${DAY_OF_WEEK:-$(date +%u)}"  # 1=Monday ... 7=Sunday (overridable for testing)
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

# Skip backup if database has no tables (migrations haven't run yet)
TABLE_COUNT=$(psql -h "${PGHOST}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
if [ "${TABLE_COUNT:-0}" -eq 0 ]; then
  echo "[$(date -Iseconds)] Skipping backup — database has no tables (migrations may not have run yet)"
  exit 0
fi

echo "[$(date -Iseconds)] Starting backup of ${PGDATABASE}@${PGHOST} (${TABLE_COUNT} tables)..."

pg_dump -h "${PGHOST}" -U "${PGUSER}" -d "${PGDATABASE}" \
  --no-owner --no-acl --clean --if-exists \
  | gzip > "${BACKUP_FILE}"

FILESIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}")
echo "[$(date -Iseconds)] Backup complete: ${BACKUP_FILE} (${FILESIZE} bytes)"

# Tag weekly backups (Sunday = day 7) by creating a symlink
if [ "${DAY_OF_WEEK}" -eq 7 ]; then
  WEEKLY_LINK="${BACKUP_DIR}/weekly_${TIMESTAMP}.sql.gz"
  ln -f "${BACKUP_FILE}" "${WEEKLY_LINK}"
  echo "[$(date -Iseconds)] Weekly backup tagged: ${WEEKLY_LINK}"
fi

# --- Rotation ---

_rotate() {
  # Rotate files matching a glob pattern, keeping the N most recent.
  # Usage: _rotate <glob_pattern> <keep_count> [inode_protect_glob]
  local pattern="$1" keep="$2" protect_glob="${3:-}"
  local files
  files=$(ls -1t ${pattern} 2>/dev/null) || return 0  # no files to rotate

  echo "${files}" | tail -n +$((keep + 1)) | while read -r old; do
    if [ -n "${protect_glob}" ]; then
      # Don't remove if a hard-link in protect_glob references the same inode
      local inode
      inode=$(stat -c%i "${old}" 2>/dev/null || stat -f%i "${old}")
      local protect_count
      protect_count=$(stat -c%i ${protect_glob} 2>/dev/null | grep -c "^${inode}$" || true)
      if [ "${protect_count:-0}" -gt 0 ]; then
        continue
      fi
    fi
    echo "[$(date -Iseconds)] Removing old backup: ${old}"
    rm -f "${old}"
  done
}

echo "[$(date -Iseconds)] Rotating daily backups (keeping last ${DAILY_KEEP})..."
_rotate "${BACKUP_DIR}/backup_*.sql.gz" "${DAILY_KEEP}" "${BACKUP_DIR}/weekly_*.sql.gz"

echo "[$(date -Iseconds)] Rotating weekly backups (keeping last ${WEEKLY_KEEP})..."
_rotate "${BACKUP_DIR}/weekly_*.sql.gz" "${WEEKLY_KEEP}"

echo "[$(date -Iseconds)] Backup and rotation finished successfully."
exit 0
