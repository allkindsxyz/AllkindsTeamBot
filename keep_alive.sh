#!/bin/bash
# Script to run the bot and keep the container alive (simplified for polling mode)

set -e

# Display some info
echo "Starting bot process at $(date)"
echo "Current directory: $(pwd)"
echo "Environment: RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT}"
echo "WEBHOOK_DOMAIN: ${WEBHOOK_DOMAIN}"
echo "RAILWAY_PUBLIC_DOMAIN: ${RAILWAY_PUBLIC_DOMAIN}"
echo "PORT: ${PORT}"

# Make prepare_env script executable and run it first if it exists
if [ -f "/app/prepare_env.sh" ]; then
  echo "Running prepare_env.sh script first..."
  chmod +x /app/prepare_env.sh
  /app/prepare_env.sh echo "Environment prepared"
fi

# Wait a bit before starting the bot
echo "Waiting 5 seconds before starting the bot..."
sleep 5

# Start the bot process - not in background since polling will keep it alive
echo "Starting bot in polling mode with: python3 -m src.bot.main"
python3 -m src.bot.main 