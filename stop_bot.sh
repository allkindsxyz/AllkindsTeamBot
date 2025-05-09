#!/bin/bash

echo "=== Stopping bot instances ==="

# Kill processes using the bot's port
echo "Checking for processes using port 8081..."
PORT_PIDS=$(lsof -i :8081 | grep -v PID | awk '{print $2}')
if [ -n "$PORT_PIDS" ]; then
    echo "Stopping processes using port 8081: $PORT_PIDS"
    echo $PORT_PIDS | xargs kill -15
    echo "Processes stopped."
else
    echo "No processes found using port 8081."
fi

# Kill Python processes running src.main
echo "Checking for Python processes running src.main..."
PYTHON_PIDS=$(ps aux | grep "python -m src.main" | grep -v grep | awk '{print $2}')
if [ -n "$PYTHON_PIDS" ]; then
    echo "Stopping Python processes: $PYTHON_PIDS"
    echo $PYTHON_PIDS | xargs kill -15
    echo "Processes stopped."
else
    echo "No Python processes found running src.main."
fi

# If a PID file exists, use it
if [ -f "bot.pid" ]; then
    echo "Found bot.pid file..."
    PID=$(cat bot.pid)
    if ps -p $PID > /dev/null; then
        echo "Stopping bot with PID $PID"
        kill -15 $PID
        sleep 2
        if ps -p $PID > /dev/null; then
            echo "Bot didn't stop gracefully, forcing termination..."
            kill -9 $PID
        fi
        echo "Bot stopped."
    else
        echo "Bot with PID $PID is not running."
    fi
    rm -f bot.pid
fi

# Remove lock file if it exists
if [ -f "bot.lock" ]; then
    echo "Removing bot.lock file..."
    rm -f bot.lock
    echo "Lock file removed."
fi

echo "=== Bot has been stopped ===" 