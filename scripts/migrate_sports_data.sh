#!/usr/bin/env bash
set -euo pipefail

# One-shot migration of existing sports tables into the new sports-data-admin Postgres.
# Usage:
#   SRC_DB=postgresql://user:pass@old-host:5432/dock108 \
#   DEST_DB=postgresql://sports:sports@localhost:5432/sports \
#   ./scripts/migrate_sports_data.sh

TABLES=(
  sports_leagues
  sports_teams
  sports_games
  sports_team_boxscores
  sports_player_boxscores
  sports_game_odds
  sports_scrape_runs
)

: "${SRC_DB:?Set SRC_DB to source Postgres URL}"
: "${DEST_DB:?Set DEST_DB to destination Postgres URL}"
if [[ "${CONFIRM_DESTRUCTIVE:-false}" != "true" ]]; then
  echo "ERROR: Destructive restore blocked."
  echo "Set CONFIRM_DESTRUCTIVE=true to proceed."
  exit 1
fi

TMP_DUMP=${TMP_DUMP:-/tmp/sports-data.dump}

echo "Dumping tables from source..."
pg_dump --format=custom --data-only $(printf -- '--table=%s ' "${TABLES[@]}") "$SRC_DB" -f "$TMP_DUMP"

echo "Restoring into destination..."
pg_restore --no-owner --no-privileges --clean --if-exists -d "$DEST_DB" "$TMP_DUMP"

echo "Done. Verify row counts on destination:"
printf '%s\n' "${TABLES[@]}" | sed 's/^/  - /'

