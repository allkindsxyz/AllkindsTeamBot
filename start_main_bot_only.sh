#!/bin/bash
set -e

# Kill any existing bot process
echo "Killing existing bot processes..."
pkill -f "python.*src.bot.main" || echo "No existing bot processes found"

# Reset webhooks and disconnect any active sessions
echo "Resetting webhooks..."
sh force_close_session.sh

# Replace hardcoded token with environment variable usage
echo "Starting main bot using BOT_TOKEN from environment variable..."
if [ -z "$BOT_TOKEN" ]; then
    echo "Error: BOT_TOKEN environment variable is not set!"
    echo "Please set it with: export BOT_TOKEN=your_bot_token"
    exit 1
fi

# Start the main bot in polling mode
echo "Starting main bot in polling mode..."
python3 -m src.bot.main > logs/main_bot_$(date '+%Y%m%d_%H%M%S').log 2>&1 &

echo "Main bot started in polling mode" 