#!/bin/bash

echo "===== RESTARTING BOT ====="

# Print what we're going to do
echo "1. Killing all Python processes running src.main"
echo "2. Killing all processes using ports 8080 and 8081"
echo "3. Removing lock files"
echo "4. Clearing API session from Telegram server"
echo "5. Starting bot with fresh instance"
echo ""

# Kill all Python processes related to the bot
echo "Killing Python processes..."
pkill -9 -f "python -m src.main" || echo "No Python processes found"
sleep 1

# Kill processes on relevant ports
echo "Killing processes on ports 8080 and 8081..."
lsof -ti :8080 | xargs kill -9 2>/dev/null || echo "No processes on port 8080"
lsof -ti :8081 | xargs kill -9 2>/dev/null || echo "No processes on port 8081"
sleep 1

# Remove all lock files
echo "Removing lock files..."
rm -f bot.lock 2>/dev/null || echo "No bot.lock file found"
find . -name "*.pid" -type f -delete 2>/dev/null
echo "Lock files removed"

# Make a curl request to Telegram to reset getUpdates
echo "Attempting to reset Telegram API session..."
BOT_TOKEN=$(grep -o 'BOT_TOKEN=[^"]*' .env | cut -d= -f2)
if [ -n "$BOT_TOKEN" ]; then
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true" > /dev/null
    echo "Telegram API session reset"
else
    echo "Warning: BOT_TOKEN not found in .env file, skipping API reset"
fi

# Wait for resources to be freed
echo "Waiting for resources to be freed..."
sleep 3

# Start the bot
echo "Starting new bot instance..."
poetry run python -m src.main 