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

# Check if the .env file exists and show its contents (without tokens)
if [ -f ".env" ]; then
  echo "Contents of .env file (showing safe variables):"
  grep -v "TOKEN\|KEY" .env | grep -v "PASSWORD\|SECRET" || echo "No safe variables found"
fi

# Print the environment variables (excluding secrets)
echo "Environment variables (showing safe variables):"
env | grep -v "TOKEN\|KEY" | grep -v "PASSWORD\|SECRET" || echo "No safe variables found"

# Wait a bit before starting the bot
echo "Waiting 5 seconds before starting the bot..."
sleep 5

# Start the bot process in the background
echo "Starting bot with: python3 -m src.bot.main"
python3 -m src.bot.main &
BOT_PID=$!

# Log the PID
echo "Bot started with PID: $BOT_PID"

# Wait for the webhook to be set up
echo "Waiting 30 seconds for webhook setup..."
sleep 30

# Check if the bot process is still running
if ps -p $BOT_PID > /dev/null; then
  echo "Bot process is still running with PID: $BOT_PID"
else
  echo "WARNING: Bot process is no longer running! It may have crashed."
  
  # Check the last few lines of the logs
  echo "Last 50 lines of logs:"
  tail -n 50 /app/logs/bot.log 2>/dev/null || echo "No log file found"
  
  # Restart the bot
  echo "Attempting to restart the bot..."
  python3 -m src.bot.main &
  BOT_PID=$!
  echo "Bot restarted with PID: $BOT_PID"
  
  # Wait again for the webhook setup
  echo "Waiting 30 more seconds for webhook setup..."
  sleep 30
fi

echo "Bot webhook should be set up now"
echo "Starting infinite loop to keep container active"

# Keep the container alive
while true; do
  echo "Container alive check at $(date)"
  
  # Check if our health endpoint is responding
  if curl -s http://localhost:8080/health > /dev/null; then
    echo "Health endpoint is responding"
  else
    echo "Health endpoint is not responding"
  fi
  
  # Check if the bot process is still running
  if ps -p $BOT_PID > /dev/null; then
    echo "Bot process is still running with PID: $BOT_PID"
  else
    echo "WARNING: Bot process is no longer running! It may have crashed."
    
    # Check the last few lines of the logs
    echo "Last 50 lines of logs:"
    tail -n 50 /app/logs/bot.log 2>/dev/null || echo "No log file found"
    
    # Restart the bot
    echo "Attempting to restart the bot..."
    python3 -m src.bot.main &
    BOT_PID=$!
    echo "Bot restarted with PID: $BOT_PID"
  fi
  
  # Use Telegram's getWebhookInfo API to check webhook status
  echo "Checking webhook info from Telegram..."
  TELEGRAM_API="https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
  curl -s "$TELEGRAM_API" | grep -v "url" # Don't show the full URL as it contains the token
  
  # Sleep for an hour
  echo "Sleeping for an hour..."
  sleep 3600
done 