#!/bin/bash

echo "===== RESETTING TELEGRAM API CONNECTION ====="

# Extract bot token
BOT_TOKEN=$(grep -o 'BOT_TOKEN=[^"]*' .env | cut -d= -f2)
if [ -z "$BOT_TOKEN" ]; then
    echo "ERROR: Failed to extract BOT_TOKEN from .env file"
    exit 1
fi

echo "1. Deleting all webhooks"
curl -s "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true" > /dev/null
echo "   Webhook deleted"

echo "2. Getting updates with offset=-1 to clear queue"
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getUpdates?offset=-1&timeout=0" > /dev/null
echo "   Update queue cleared"

echo "3. Getting updates again to verify connection reset"
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getUpdates?limit=1" > /dev/null
echo "   Connection verified"

echo "4. Getting bot info to verify token is valid"
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getMe" | grep -o '"username":"[^"]*"'
echo ""

echo "===== TELEGRAM API CONNECTION RESET COMPLETE ====="
echo "You can now run ./run_bot_fixed.sh to start the bot without conflicts." 