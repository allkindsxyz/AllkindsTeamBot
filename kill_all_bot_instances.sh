#!/bin/bash

echo "===== KILLING ALL BOT INSTANCES ====="

# Find and kill all Python processes that might be related to the bot
echo "Finding and killing all Python processes that could be related to the bot..."
pkill -9 -f "python" && echo "Killed all Python processes" || echo "No Python processes found"
sleep 1

# Find and kill all processes on common ports
echo "Killing all processes on ports 8080, 8081, and other common ports..."
for port in 8080 8081 5000 5432 6379; do
    lsof -ti :$port | xargs kill -9 2>/dev/null && echo "Killed process on port $port" || echo "No process on port $port"
done
sleep 1

# Remove all possible lock and PID files
echo "Removing all lock and PID files..."
rm -f bot.lock *.pid ./*.pid ./src/*.pid 2>/dev/null
find . -name "*.pid" -type f -delete 2>/dev/null
find . -name "*.lock" -type f -delete 2>/dev/null
echo "All lock and PID files removed"

# Reset the Telegram API connection
echo "Resetting Telegram API connection..."
BOT_TOKEN=$(grep -o 'BOT_TOKEN=[^"]*' .env | cut -d= -f2)
if [ -n "$BOT_TOKEN" ]; then
    # Delete webhook
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true" > /dev/null
    echo "Deleted webhook and pending updates"
    
    # Get updates with timeout=0 to clear the update queue
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/getUpdates?offset=-1&timeout=0" > /dev/null
    echo "Cleared update queue"
    
    # Get updates with a negative offset to reset the connection
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/getUpdates?offset=-1" > /dev/null
    echo "Reset Telegram API connection"
else
    echo "Warning: BOT_TOKEN not found in .env file, skipping API reset"
fi

# Forcefully close all network connections related to Telegram
echo "Closing all network connections to api.telegram.org..."
lsof -i | grep telegram | awk '{print $2}' | xargs kill -9 2>/dev/null || echo "No connections to Telegram found"

# Wait for all resources to be freed
echo "Waiting for all resources to be freed..."
sleep 5

echo "===== ALL BOT INSTANCES KILLED =====" 