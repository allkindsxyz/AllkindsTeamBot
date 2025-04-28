#!/bin/bash
# Debug mode script for AllkindsTeamBot
# Run this script to test the bot in debug mode with enhanced logging

# Set environment variables for debugging
export LOG_LEVEL=DEBUG
export USE_WEBHOOK=false
export PYTHONPATH=$(pwd)

# Automatically load .env file if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env file"
    export $(grep -v '^#' .env | xargs)
fi

# Kill any existing bot processes to avoid conflicts
echo "Stopping any existing bot processes..."
pkill -f "python.*src.bot.main" || true
sleep 2

# Create logs directory if it doesn't exist
mkdir -p logs

# Get current timestamp for log file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/debug_bot_$TIMESTAMP.log"

echo "Starting bot in debug mode..."
echo "Logs will be saved to $LOG_FILE"
echo "Press Ctrl+C to stop the bot"

# Run the bot with output to both console and log file
python3 -m src.bot.main 2>&1 | tee "$LOG_FILE" 