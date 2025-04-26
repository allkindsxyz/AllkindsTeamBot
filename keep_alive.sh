#!/bin/bash
# Script to run the bot and keep the container alive

set -e

# Display some info
echo "Starting bot process at $(date)"
echo "Current directory: $(pwd)"

# Start the bot process in the background
python3 -m src.bot.main &
BOT_PID=$!

# Log the PID
echo "Bot started with PID: $BOT_PID"

# Wait a bit for the webhook to be set up
sleep 30

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
  # Sleep for an hour
  sleep 3600
done 