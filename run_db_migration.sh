#!/bin/bash
set -e

echo "Starting database migration process using Docker..."

# Build the migration Docker image
echo "Building migration Docker image..."
docker build -f migration-dockerfile -t allkinds-migration .

# Run the migration with the DATABASE_URL from Railway
echo "Running migration..."
docker run --rm -e DATABASE_URL="$DATABASE_URL" allkinds-migration

echo "Migration process completed" 