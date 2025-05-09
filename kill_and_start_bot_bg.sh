#!/bin/bash

echo "=== Killing existing bot instances ==="

# Kill processes using the bot's port
echo "Checking for processes using port 8081..."
PORT_PIDS=$(lsof -i :8081 | grep -v PID | awk '{print $2}')
if [ -n "$PORT_PIDS" ]; then
    echo "Killing processes using port 8081: $PORT_PIDS"
    echo $PORT_PIDS | xargs kill -9
    echo "Processes killed."
else
    echo "No processes found using port 8081."
fi

# Kill Python processes running src.main
echo "Checking for Python processes running src.main..."
PYTHON_PIDS=$(ps aux | grep "python -m src.main" | grep -v grep | awk '{print $2}')
if [ -n "$PYTHON_PIDS" ]; then
    echo "Killing Python processes: $PYTHON_PIDS"
    echo $PYTHON_PIDS | xargs kill -9
    echo "Processes killed."
else
    echo "No Python processes found running src.main."
fi

# Remove lock file if it exists
if [ -f "bot.lock" ]; then
    echo "Removing bot.lock file..."
    rm -f bot.lock
    echo "Lock file removed."
fi

# Wait a moment to ensure ports are freed
echo "Waiting for resources to be freed..."
sleep 2

# Start the bot in the background
echo "=== Starting new bot instance in background ==="
nohup poetry run python -m src.main > bot.log 2>&1 &

# Store the PID
echo $! > bot.pid
echo "Bot started with PID $(cat bot.pid)"
echo "Logs are being written to bot.log" 