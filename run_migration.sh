#!/bin/bash
echo "Running migration script..."
echo "Current environment:"
printenv | grep -i database

echo "Migration will now attempt to run..."
python3 run_match_migration.py

./deploy_to_railway.sh 