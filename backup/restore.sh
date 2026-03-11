#!/usr/bin/env bash
# Restore a PostgreSQL database from a gzipped pg_dump backup.
# Usage: restore.sh [BACKUP_FILE] [--yes]
#
# If no file is given, restores the latest backup from /backups.
# Environment: PGHOST, PGUSER, PGPASSWORD, PGDATABASE (set by docker-compose)
set -euo pipefail

BACKUP_DIR="/backups"
AUTO_CONFIRM=false
BACKUP_FILE=""

for arg in "$@"; do
  case "${arg}" in
    --yes) AUTO_CONFIRM=true ;;
    *) BACKUP_FILE="${arg}" ;;
  esac
done

# Default to latest backup if none specified
if [ -z "${BACKUP_FILE}" ]; then
  BACKUP_FILE=$(ls -1t "${BACKUP_DIR}"/backup_*.sql.gz 2>/dev/null | head -n1 || true)
  if [ -z "${BACKUP_FILE}" ]; then
    echo "ERROR: No backup files found in ${BACKUP_DIR}" >&2
    exit 1
  fi
  echo "Using latest backup: ${BACKUP_FILE}"
fi

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "ERROR: Backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

FILESIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}")
echo "Backup file: ${BACKUP_FILE} (${FILESIZE} bytes)"
echo "Target database: ${PGDATABASE}@${PGHOST}"

if [ "${AUTO_CONFIRM}" != true ]; then
  echo ""
  echo "WARNING: This will DROP and RECREATE the database '${PGDATABASE}'."
  read -r -p "Continue? [y/N] " confirm
  if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "[$(date -Iseconds)] Dropping database ${PGDATABASE}..."
# Terminate existing connections and drop
psql -h "${PGHOST}" -U "${PGUSER}" -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${PGDATABASE}' AND pid <> pg_backend_pid();" \
  > /dev/null 2>&1 || true

dropdb -h "${PGHOST}" -U "${PGUSER}" --if-exists "${PGDATABASE}"

echo "[$(date -Iseconds)] Creating database ${PGDATABASE}..."
createdb -h "${PGHOST}" -U "${PGUSER}" "${PGDATABASE}"

echo "[$(date -Iseconds)] Restoring from ${BACKUP_FILE}..."
gunzip -c "${BACKUP_FILE}" | psql -h "${PGHOST}" -U "${PGUSER}" -d "${PGDATABASE}" --quiet -1

# Verify by checking table count
TABLE_COUNT=$(psql -h "${PGHOST}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")

echo "[$(date -Iseconds)] Restore complete. Tables found: ${TABLE_COUNT}"

if [ "${TABLE_COUNT}" -gt 0 ]; then
  echo "Verification PASSED: database has ${TABLE_COUNT} table(s)."
  exit 0
else
  echo "Verification FAILED: no tables found after restore." >&2
  exit 1
fi
