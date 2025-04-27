#!/bin/bash

# Script to run the simplified bot with proper error handling
set -e

echo "===================================="
echo "Starting simplified Allkinds bot..."
echo "===================================="
echo "Environment: $RAILWAY_ENVIRONMENT"
echo "Current directory: $(pwd)"
echo "Date/time: $(date)"
echo "===================================="

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found! Please install Python 3.8 or higher."
    exit 1
fi

# Check for required files
if [ ! -f "simple_bot.py" ]; then
    echo "ERROR: simple_bot.py not found in current directory!"
    ls -la
    exit 1
fi

# Make sure the script is executable
chmod +x simple_bot.py

# Function to cleanup on exit
cleanup() {
    echo "Cleaning up..."
    # Kill any running bot processes
    if [ -n "$BOT_PID" ]; then
        echo "Killing bot process $BOT_PID"
        kill -TERM "$BOT_PID" 2>/dev/null || true
    fi
    echo "Cleanup complete."
}

# Set trap for cleanup on exit
trap cleanup EXIT INT TERM

# Start the bot in foreground
echo "Starting simplified bot..."
python3 simple_bot.py &
BOT_PID=$!

# Log the PID
echo "Bot started with PID: $BOT_PID"

# Monitor the process
echo "Monitoring bot process..."
while kill -0 $BOT_PID 2>/dev/null; do
    echo "[$(date)] Bot is running with PID $BOT_PID"
    sleep 60
done

# If we get here, the bot exited
echo "ALERT: Bot process $BOT_PID has exited unexpectedly!"
echo "Attempting restart..."

# Restart the bot
exec "$0" "$@" 