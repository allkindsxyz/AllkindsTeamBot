#!/bin/bash

# Kill any existing Python processes related to the bots
echo "Killing any existing bot processes..."
pkill -f "python3 -m src.bot.main" || true
pkill -f "python3 -m src.communicator_bot.main" || true
sleep 2

# Bot tokens
MAIN_BOT_TOKEN="8155919814:AAEMO6RHdkcBErONs70UNjBw4XEvN2vqJuo"

# Try multiple methods to close existing sessions
echo "Forcefully disconnecting any active Telegram sessions..."

# Method 1: Force disconnect and close session, drop pending updates
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

# Method 2: Try with offset parameter which can help close long-polling connections
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/getUpdates?offset=-1&timeout=1"
echo -e "\n"

# Method 3: Get an update with higher offset to mark all previous ones as read
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/getUpdates?offset=999999999&timeout=1"
echo -e "\n"

# Verify webhook info
echo "Main bot webhook info:"
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/getWebhookInfo"
echo -e "\n"

# Wait before attempting to start
echo "Waiting 5 seconds before starting..."
sleep 5

# Start only the main bot
echo "Starting main bot..."
python3 -m src.bot.main > main_bot.log 2>&1 &
MAIN_BOT_PID=$!
echo "Main bot started with PID: $MAIN_BOT_PID"
echo "Main bot PID saved to main_bot_pid.txt"

# Save PID to a file for easy stopping later
echo "$MAIN_BOT_PID" > main_bot_pid.txt

echo "Main bot should be starting. Check main_bot.log for output."
echo "To stop the bot, run: kill $(cat main_bot_pid.txt)" 