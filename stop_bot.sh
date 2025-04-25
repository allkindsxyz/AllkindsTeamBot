#!/bin/bash
echo "Stopping bot and cleaning up..."

# Find bot process
BOT_PID=$(ps aux | grep "python run.py" | grep -v grep | awk '{print $2}')

if [ -n "$BOT_PID" ]; then
    echo "Found bot process (PID: $BOT_PID), terminating..."
    kill -15 $BOT_PID
    sleep 2
    
    # Check if process is still running
    if ps -p $BOT_PID > /dev/null; then
        echo "Process didn't terminate gracefully, forcing..."
        kill -9 $BOT_PID
    fi
    
    echo "Bot terminated successfully"
else
    echo "No running bot process found"
fi

# Reset webhook
echo "Resetting webhook..."
curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true"

echo "Cleanup complete" 