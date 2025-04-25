#!/bin/bash

# Load environment variables if .env file exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Check if environment variables are set
if [ -z "$BOT_TOKEN" ]; then
    echo "Error: BOT_TOKEN environment variable is not set."
    echo "Please set it before running this script or create a .env file."
    exit 1
fi

if [ -z "$COMMUNICATOR_BOT_TOKEN" ]; then
    echo "Error: COMMUNICATOR_BOT_TOKEN environment variable is not set."
    echo "Please set it before running this script or create a .env file."
    exit 1
fi

# Use environment variables for tokens
MAIN_BOT_TOKEN="$BOT_TOKEN"
COMMUNICATOR_BOT_TOKEN="$COMMUNICATOR_BOT_TOKEN"

# Kill any existing bots
echo "Killing any running bots..."
pkill -f "python3 -m src.bot.main" || true
pkill -f "python3 -m src.communicator_bot.main" || true
sleep 2

# Close the session for main bot by using getUpdates with timeout=0
echo "Closing main bot session..."
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/getUpdates?timeout=0&offset=-1"
echo -e "\n"

# Close the session for communicator bot
echo "Closing communicator bot session..."
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/getUpdates?timeout=0&offset=-1"
echo -e "\n"

# Delete webhook for main bot
echo "Resetting main bot webhook..."
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

# Delete webhook for communicator bot
echo "Resetting communicator bot webhook..."
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

echo "Done! Now try running the bots again." 