#!/bin/bash
# Railway startup script

# Log the startup
echo "Starting AllkindsTeamBot services..."

# Give the system a moment to stabilize
sleep 3

# Start the main bot
python -m src.main &
MAIN_PID=$!
echo "Main bot started with PID $MAIN_PID"

# Start the communicator bot
python -m src.communicator_bot.main &
COMM_PID=$!
echo "Communicator bot started with PID $COMM_PID"

# Monitor the processes
monitor() {
  echo "Monitoring processes..."
  while true; do
    if ! kill -0 $MAIN_PID 2>/dev/null; then
      echo "Main bot process died, restarting..."
      python -m src.main &
      MAIN_PID=$!
    fi
    
    if ! kill -0 $COMM_PID 2>/dev/null; then
      echo "Communicator bot process died, restarting..."
      python -m src.communicator_bot.main &
      COMM_PID=$!
    fi
    
    sleep 10
  done
}

# Start the monitor in the background
monitor &
MONITOR_PID=$!

# Wait for all processes
wait
