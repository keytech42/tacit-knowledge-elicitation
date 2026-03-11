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
DAY_OF_WEEK=$(date +%u)  # 1=Monday ... 7=Sunday
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Starting backup of ${PGDATABASE}@${PGHOST}..."

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

# Remove daily backups older than DAILY_KEEP days (exclude weekly links)
echo "[$(date -Iseconds)] Rotating daily backups (keeping last ${DAILY_KEEP})..."
ls -1t "${BACKUP_DIR}"/backup_*.sql.gz 2>/dev/null \
  | tail -n +$((DAILY_KEEP + 1)) \
  | while read -r old; do
      # Don't remove if a weekly hard-link still references the same inode
      INODE=$(stat -c%i "${old}" 2>/dev/null || stat -f%i "${old}")
      WEEKLY_COUNT=$(stat -c%i "${BACKUP_DIR}"/weekly_*.sql.gz 2>/dev/null | grep -c "^${INODE}$" || true)
      if [ "${WEEKLY_COUNT:-0}" -eq 0 ]; then
        echo "[$(date -Iseconds)] Removing old daily backup: ${old}"
        rm -f "${old}"
      fi
    done

# Remove weekly backups beyond WEEKLY_KEEP
echo "[$(date -Iseconds)] Rotating weekly backups (keeping last ${WEEKLY_KEEP})..."
ls -1t "${BACKUP_DIR}"/weekly_*.sql.gz 2>/dev/null \
  | tail -n +$((WEEKLY_KEEP + 1)) \
  | while read -r old; do
      echo "[$(date -Iseconds)] Removing old weekly backup: ${old}"
      rm -f "${old}"
    done

echo "[$(date -Iseconds)] Backup and rotation finished successfully."
exit 0
