#!/bin/bash
# Script to reset the database on Railway

echo "Making scripts executable..."
chmod +x drop_production_db.py

echo "Committing changes..."
git add drop_production_db.py railway_reset_db.sh
git commit -m "Add database reset scripts"
git push

echo "Deploying to Railway..."
if command -v railway &> /dev/null; then
    echo "Running database reset script on Railway..."
    railway run --service allkinds-team-bot python3 drop_production_db.py
else
    echo "Railway CLI not found. Please install it with: npm i -g @railway/cli"
    echo "Then login with: railway login"
    echo "After that, run this script again."
    exit 1
fi

echo "Done!" 