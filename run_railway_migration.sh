#!/bin/bash
set -e

echo "Running one-off migration command on Railway..."

# Export the railway command that will be executed
echo "python run_match_migration.py" > migration_command.txt

# Execute the migration directly on Railway
railway run --service $SERVICE_NAME python run_match_migration.py

echo "Migration completed" 