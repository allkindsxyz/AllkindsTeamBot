#!/bin/bash
set -e

echo "==============================================="
echo "AllKinds Railway Deployment Script"
echo "==============================================="

# Ensure Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "Railway CLI not found. Please install it first:"
    echo "npm i -g @railway/cli"
    exit 1
fi

# Check if logged in to Railway
railway whoami || railway login

# Set the project
echo "Setting up Railway project..."
railway link

# Run migration directly with our simplified script
echo "Running database migration..."
python3 railway_migration.py

# Confirm before proceeding with deployment
read -p "Do you want to proceed with deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment aborted."
    exit 1
fi

# Deploy to Railway
echo "Deploying to Railway..."
railway up

echo "==============================================="
echo "Deployment complete!"
echo "===============================================" 