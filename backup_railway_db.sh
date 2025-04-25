#!/bin/bash
set -e

echo "Creating PostgreSQL backup from Railway..."

# Generate backup filename
BACKUP_FILE="allkinds_backup_$(date +%Y%m%d_%H%M%S).dump"
echo "Backup will be saved to: $BACKUP_FILE"

# Make sure psql is installed
if ! command -v psql &> /dev/null; then
    echo "PostgreSQL client tools not found. Please install them first."
    exit 1
fi

# Run this directly on Railway using the DATABASE_URL environment variable
echo "Running backup using Railway CLI..."
railway run -s Postgres --environment production \
  "pg_dump \$DATABASE_URL --format=custom --no-owner --no-acl" > "$BACKUP_FILE"

if [ $? -eq 0 ] && [ -s "$BACKUP_FILE" ]; then
    echo "✅ Backup created successfully: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
else
    echo "❌ Backup failed or file is empty"
    exit 1
fi 