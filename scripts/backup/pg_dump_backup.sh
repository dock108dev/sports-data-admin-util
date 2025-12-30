#!/usr/bin/env bash
set -euo pipefail

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
backup_dir="${BACKUP_DIR:-/var/backups/sports}"
backup_name="sports_${timestamp}.sql.gz"
backup_path="${backup_dir}/${backup_name}"

mkdir -p "${backup_dir}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL must be set for backups." >&2
  exit 1
fi

echo "Starting backup to ${backup_path}"
pg_dump "${DATABASE_URL}" | gzip > "${backup_path}"

if [[ -n "${BACKUP_S3_URI:-}" ]]; then
  echo "Uploading backup to ${BACKUP_S3_URI}"
  aws s3 cp "${backup_path}" "${BACKUP_S3_URI%/}/${backup_name}"
fi

if [[ -n "${BACKUP_RCLONE_REMOTE:-}" ]]; then
  echo "Uploading backup to ${BACKUP_RCLONE_REMOTE}"
  rclone copy "${backup_path}" "${BACKUP_RCLONE_REMOTE}"
fi

echo "Backup completed."
