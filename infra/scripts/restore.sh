#!/bin/bash
set -euo pipefail

# Restore database from backup file
# Usage: /scripts/restore.sh [backup_file]
# Example: docker exec -i sports-postgres /scripts/restore.sh /backups/sports_20260108_120000.sql.gz

BACKUP_FILE="${1:-/backups/latest.sql.gz}"
if [[ "${CONFIRM_DESTRUCTIVE:-false}" != "true" ]]; then
    echo "ERROR: Destructive restore blocked."
    echo "Set CONFIRM_DESTRUCTIVE=true to proceed."
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    echo ""
    echo "Available backups:"
    ls -la /backups/*.sql.gz 2>/dev/null || echo "  No backups found"
    exit 1
fi

echo "Restoring from: $BACKUP_FILE"
echo "Database: ${POSTGRES_DB:-sports}"
echo ""
echo "WARNING: This will overwrite all data in the database!"
echo "Press Ctrl+C within 5 seconds to cancel..."
sleep 5

echo "Starting restore..."

# Drop and recreate database to ensure clean state
#
# Postgres 16+ supports DROP DATABASE ... WITH (FORCE) to terminate sessions.
# This avoids fragile manual container stop ordering during local restores.
psql -U "${POSTGRES_USER:-sports}" -d postgres -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-sports} WITH (FORCE);"
psql -U "${POSTGRES_USER:-sports}" -d postgres -c "CREATE DATABASE ${POSTGRES_DB:-sports};"

# Restore from backup
gunzip -c "$BACKUP_FILE" | psql -U "${POSTGRES_USER:-sports}" -d "${POSTGRES_DB:-sports}"

echo ""
echo "Restore complete!"
echo "Verify with: docker exec sports-postgres psql -U ${POSTGRES_USER:-sports} -d ${POSTGRES_DB:-sports} -c 'SELECT COUNT(*) FROM sports_games;'"
