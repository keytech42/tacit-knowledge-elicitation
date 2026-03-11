#!/usr/bin/env bash
# Verify a backup by restoring it into a temporary database and checking tables.
# Usage: verify.sh [BACKUP_DIR]
#
# Environment: PGHOST, PGUSER, PGPASSWORD, PGDATABASE (set by docker-compose)
set -euo pipefail

BACKUP_DIR="${1:-/backups}"
TEMP_DB="${PGDATABASE}_verify_$$"

# Find latest backup
BACKUP_FILE=$(ls -1t "${BACKUP_DIR}"/backup_*.sql.gz 2>/dev/null | head -n1 || true)
if [ -z "${BACKUP_FILE}" ]; then
  echo "ERROR: No backup files found in ${BACKUP_DIR}" >&2
  exit 1
fi

echo "[$(date -Iseconds)] Verifying backup: ${BACKUP_FILE}"
echo "[$(date -Iseconds)] Temporary database: ${TEMP_DB}"

cleanup() {
  echo "[$(date -Iseconds)] Cleaning up temporary database ${TEMP_DB}..."
  dropdb -h "${PGHOST}" -U "${PGUSER}" --if-exists "${TEMP_DB}" 2>/dev/null || true
}
trap cleanup EXIT

# Get expected table count from the live database
EXPECTED_TABLES=$(psql -h "${PGHOST}" -U "${PGUSER}" -d "${PGDATABASE}" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")

echo "[$(date -Iseconds)] Expected tables (from live DB): ${EXPECTED_TABLES}"

# Create temporary database
echo "[$(date -Iseconds)] Creating temporary database..."
createdb -h "${PGHOST}" -U "${PGUSER}" "${TEMP_DB}"

# Restore into temp database
echo "[$(date -Iseconds)] Restoring backup into temporary database..."
gunzip -c "${BACKUP_FILE}" | psql -h "${PGHOST}" -U "${PGUSER}" -d "${TEMP_DB}" --quiet -1

# Count restored tables
RESTORED_TABLES=$(psql -h "${PGHOST}" -U "${PGUSER}" -d "${TEMP_DB}" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")

echo "[$(date -Iseconds)] Restored tables: ${RESTORED_TABLES}"

# Compare
if [ "${RESTORED_TABLES}" -eq "${EXPECTED_TABLES}" ] && [ "${RESTORED_TABLES}" -gt 0 ]; then
  echo "[$(date -Iseconds)] PASS: Backup verification successful (${RESTORED_TABLES}/${EXPECTED_TABLES} tables)"
  exit 0
else
  echo "[$(date -Iseconds)] FAIL: Table count mismatch (restored: ${RESTORED_TABLES}, expected: ${EXPECTED_TABLES})" >&2
  exit 1
fi
