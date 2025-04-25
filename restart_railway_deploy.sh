#!/bin/bash
# Railway deployment restart script
# This script helps restart a failed deployment with proper cleanup

echo "===== RAILWAY DEPLOYMENT RESTART SCRIPT ====="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "Railway CLI not found. Please install it first:"
    echo "npm install -g @railway/cli"
    exit 1
fi

# Check if logged in to Railway
echo "Checking Railway login status..."
if ! railway whoami &> /dev/null; then
    echo "Not logged in to Railway. Please run 'railway login' first."
    exit 1
fi

echo "Currently logged in as: $(railway whoami)"
echo "Current project: $(railway environment)"

# Verify we want to proceed
read -p "Are you sure you want to restart the deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Operation cancelled."
    exit 1
fi

# Commit and push the fix
echo "Committing the fix to database connection..."
git add src/db/base.py
git commit -m "Fix: Remove host override in database connection"

echo "Pushing to remote repository..."
git push

# Deploy the changes
echo "Deploying changes to Railway..."
railway up

# Check deployment status
echo "Checking deployment status..."
sleep 10  # Wait for deployment to start

# Function to get deployment ID
get_deployment_id() {
    railway status --json | jq -r '.deployments[0].id'
}

# Get the deployment ID
DEPLOYMENT_ID=$(get_deployment_id)
if [ -z "$DEPLOYMENT_ID" ] || [ "$DEPLOYMENT_ID" == "null" ]; then
    echo "Failed to get deployment ID. Please check manually with 'railway status'."
    exit 1
fi

echo "Monitoring deployment $DEPLOYMENT_ID..."

# Poll deployment status
while true; do
    STATUS=$(railway status --json | jq -r ".deployments[] | select(.id == \"$DEPLOYMENT_ID\") | .status")
    
    if [ "$STATUS" == "FAILED" ]; then
        echo "Deployment failed."
        break
    elif [ "$STATUS" == "SUCCESS" ]; then
        echo "Deployment successful!"
        break
    elif [ "$STATUS" == "BUILDING" ] || [ "$STATUS" == "DEPLOYING" ]; then
        echo "Deployment in progress: $STATUS"
    else
        echo "Deployment status: $STATUS"
    fi
    
    sleep 10
done

# Check logs if deployment failed
if [ "$STATUS" == "FAILED" ]; then
    echo "Fetching logs for failed deployment..."
    railway logs --deployment "$DEPLOYMENT_ID"
    
    echo "Running diagnostic script..."
    python db_connection_test.py
    
    echo "Consider these troubleshooting steps:"
    echo "1. Check if DATABASE_URL is correct in Railway variables"
    echo "2. Try restarting the database service: railway service restart <database-service-name>"
    echo "3. Check if there are any IP restrictions on the database"
else
    echo "Running diagnostic checks on successful deployment..."
    python check_webhook.py
    
    echo "Testing Telegram bot..."
    python test_telegram.py
fi

echo "Deployment restart process completed!" 