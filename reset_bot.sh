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

# Delete webhook and pending updates for main bot
echo "Resetting main bot webhook..."
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

# Delete webhook and pending updates for communicator bot
echo "Resetting communicator bot webhook..."
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

# Get webhook info for main bot
echo "Main bot webhook info:"
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/getWebhookInfo"
echo -e "\n"

# Get webhook info for communicator bot
echo "Communicator bot webhook info:"
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/getWebhookInfo"
echo -e "\n"

echo "Done! Now try running the bots again." 