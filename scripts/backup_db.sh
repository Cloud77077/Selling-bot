#!/usr/bin/env bash
set -euo pipefail
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
DB_URL=${DATABASE_URL:-sqlite:///./selling_bot.db}
if [[ "$DB_URL" == sqlite* ]]; then
  DB_FILE=${DB_URL#sqlite:///}
  cp "$DB_FILE" "backups/sqlite-$STAMP.db"
  echo "SQLite backup: backups/sqlite-$STAMP.db"
else
  pg_dump "$DB_URL" | gzip > "backups/postgres-$STAMP.sql.gz"
  echo "PostgreSQL backup: backups/postgres-$STAMP.sql.gz"
fi
