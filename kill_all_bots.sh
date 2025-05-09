#!/bin/bash

echo "===== KILLING ALL BOT PROCESSES ====="

# Check for Python processes running src.main
echo "Checking for Python processes running src.main..."
PYTHON_PIDS=$(ps aux | grep "python -m src.main" | grep -v grep | awk '{print $2}')
if [ -n "$PYTHON_PIDS" ]; then
    echo "Found Python processes: $PYTHON_PIDS"
    # Try SIGTERM first for clean shutdown
    echo "Sending SIGTERM..."
    echo $PYTHON_PIDS | xargs kill -15
    sleep 3
    
    # Check if processes are still running
    REMAINING=$(ps aux | grep "python -m src.main" | grep -v grep | awk '{print $2}')
    if [ -n "$REMAINING" ]; then
        echo "Some processes still running, using SIGKILL..."
        echo $REMAINING | xargs kill -9
    fi
    echo "Python processes terminated."
else
    echo "No Python processes found running src.main."
fi

# Check for processes using port 8081 (bot API)
echo "Checking for processes using port 8081..."
PORT_PIDS=$(lsof -i :8081 | grep -v PID | awk '{print $2}')
if [ -n "$PORT_PIDS" ]; then
    echo "Found processes using port 8081: $PORT_PIDS"
    # Try SIGTERM first for clean shutdown
    echo "Sending SIGTERM..."
    echo $PORT_PIDS | xargs kill -15
    sleep 3
    
    # Check if processes are still running
    REMAINING=$(lsof -i :8081 | grep -v PID | awk '{print $2}')
    if [ -n "$REMAINING" ]; then
        echo "Some processes still using port, using SIGKILL..."
        echo $REMAINING | xargs kill -9
    fi
    echo "Port 8081 processes terminated."
else
    echo "No processes found using port 8081."
fi

# Check for processes using port 8080 (health check)
echo "Checking for processes using port 8080..."
PORT_PIDS=$(lsof -i :8080 | grep -v PID | awk '{print $2}')
if [ -n "$PORT_PIDS" ]; then
    echo "Found processes using port 8080: $PORT_PIDS"
    # Try SIGTERM first for clean shutdown
    echo "Sending SIGTERM..."
    echo $PORT_PIDS | xargs kill -15
    sleep 3
    
    # Check if processes are still running
    REMAINING=$(lsof -i :8080 | grep -v PID | awk '{print $2}')
    if [ -n "$REMAINING" ]; then
        echo "Some processes still using port, using SIGKILL..."
        echo $REMAINING | xargs kill -9
    fi
    echo "Port 8080 processes terminated."
else
    echo "No processes found using port 8080."
fi

# Remove lock file if it exists
if [ -f "bot.lock" ]; then
    echo "Removing bot.lock file..."
    rm -f bot.lock
    echo "Lock file removed."
fi

# Remove any PID files
find . -name "*.pid" -type f -delete
echo "Removed any PID files"

# Wait a moment to ensure resources are freed
echo "Waiting for resources to be freed..."
sleep 2

echo "===== ALL BOT PROCESSES KILLED =====" 