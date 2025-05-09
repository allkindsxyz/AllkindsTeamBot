#!/bin/bash

echo "===== STARTING BOT ====="

# First, kill all existing processes
echo "Killing existing processes..."
pkill -f "python -m src.main" 2>/dev/null
lsof -i :8081 | grep -v PID | awk '{print $2}' | xargs kill -9 2>/dev/null
lsof -i :8080 | grep -v PID | awk '{print $2}' | xargs kill -9 2>/dev/null

# Remove lock files
echo "Removing lock files..."
rm -f bot.lock 2>/dev/null
find . -name "*.pid" -type f -delete 2>/dev/null

# Wait for resources to be freed
echo "Waiting for resources to be freed..."
sleep 2

# Run the bot
echo "Starting bot (press Ctrl+C to stop)..."
poetry run python -m src.main 