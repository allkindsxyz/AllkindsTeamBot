#!/bin/bash
# Script to run the bot and keep the container alive

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

# Fix asyncpg installation before starting the bot
if [ -f "/app/pip_install_asyncpg.sh" ]; then
  echo "Running asyncpg installation fix..."
  chmod +x /app/pip_install_asyncpg.sh
  /app/pip_install_asyncpg.sh
  echo "Asyncpg installation fixed."
fi

# Wait a bit before starting the bot
echo "Waiting 5 seconds before starting the bot..."
sleep 5

# Start the bot process in the background with USE_WEBHOOK=0 to force polling mode
echo "Starting bot in polling mode with: USE_WEBHOOK=0 python3 -m src.bot.main"
USE_WEBHOOK=0 nohup python3 -m src.bot.main > bot.log 2>&1 &
BOT_PID=$!
echo "Bot started with PID: $BOT_PID"

# Set up log monitor in the background
(tail -f bot.log &)

# Start the health check server
echo "Starting health check server to keep the container active"
python3 health_server.py 