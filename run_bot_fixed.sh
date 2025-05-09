#!/bin/bash

echo "===== RUNNING BOT WITH CONFLICT PREVENTION ====="

# Step 1: Kill all existing bot instances
echo "[1/5] Cleaning up existing processes..."
./kill_all_bot_instances.sh

# Step 2: Set a lock to prevent multiple instances
echo "[2/5] Setting up a safe lock mechanism..."
if [ -f "bot.lock" ]; then
    echo "ERROR: Lock file already exists. Another process might be running."
    echo "If you're sure no other process is running, delete bot.lock and try again."
    exit 1
fi

echo "[3/5] Creating lock file..."
echo "{\"started_at\": \"$(date)\", \"pid\": $$}" > bot.lock

# Step 3: Reset Telegram API state
echo "[4/5] Ensuring clean Telegram API state..."
BOT_TOKEN=$(grep -o 'BOT_TOKEN=[^"]*' .env | cut -d= -f2)
if [ -n "$BOT_TOKEN" ]; then
    echo "- Deleting webhook..."
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true" > /dev/null
    echo "- Resetting update queue..."
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/getUpdates?offset=-1&timeout=0" > /dev/null
    echo "Telegram API state reset successfully"
else
    echo "WARNING: BOT_TOKEN not found in .env"
fi

# Step 4: Start the bot with a clean environment
echo "[5/5] Starting bot with clean environment..."
echo "Starting bot. Press Ctrl+C to stop."
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    rm -f bot.lock
    echo "Lock file removed."
    exit 0
}

# Register trap for cleanup
trap cleanup SIGINT SIGTERM

# Run the bot
PYTHONUNBUFFERED=1 poetry run python -m src.main

# If we get here, the bot has exited
cleanup 