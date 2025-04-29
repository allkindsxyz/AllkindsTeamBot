#!/bin/bash
# Railway startup script

# Log the startup
echo "Starting AllkindsTeamBot services..."

# Function to send health check to Railway to prevent service from being marked as "completed"
health_check() {
  echo "Starting health check server..."
  while true; do
    echo "Health check ping: $(date)"
    # Touch a file to show activity
    touch /tmp/railway_alive
    sleep 30
  done
}

# Start the health check in the background
health_check &
HEALTH_PID=$!
echo "Health check started with PID $HEALTH_PID"

# Give the system and database a moment to stabilize
echo "Waiting for database to become available..."
sleep 15

# Start the main bot
python -m src.main &
MAIN_PID=$!
echo "Main bot started with PID $MAIN_PID"

# Start the communicator bot
python -m src.communicator_bot.main &
COMM_PID=$!
echo "Communicator bot started with PID $COMM_PID"

# Monitor the processes with improved error logging
monitor() {
  echo "Monitoring processes..."
  while true; do
    if ! kill -0 $MAIN_PID 2>/dev/null; then
      echo "Main bot process died (PID $MAIN_PID), waiting before restarting..."
      echo "Checking for potential errors in logs..."
      tail -n 50 /tmp/main_bot_error.log 2>/dev/null || echo "No error log found"
      sleep 5
      echo "Restarting main bot..."
      python -m src.main > /tmp/main_bot_output.log 2> /tmp/main_bot_error.log &
      MAIN_PID=$!
      echo "Main bot restarted with new PID $MAIN_PID"
    fi
    
    if ! kill -0 $COMM_PID 2>/dev/null; then
      echo "Communicator bot process died (PID $COMM_PID), waiting before restarting..."
      echo "Checking for potential errors in logs..."
      tail -n 50 /tmp/comm_bot_error.log 2>/dev/null || echo "No error log found"
      sleep 8
      echo "Restarting communicator bot..."
      python -m src.communicator_bot.main > /tmp/comm_bot_output.log 2> /tmp/comm_bot_error.log &
      COMM_PID=$!
      echo "Communicator bot restarted with new PID $COMM_PID"
    fi
    
    # Print a periodic status message to show the script is still running
    echo "$(date): Bots running - Main: $MAIN_PID, Communicator: $COMM_PID"
    
    sleep 10
  done
}

# Trap signals to ensure proper cleanup
trap 'echo "Received termination signal"; kill $MAIN_PID $COMM_PID $HEALTH_PID 2>/dev/null' SIGTERM SIGINT

# Start the monitor in the background
monitor &
MONITOR_PID=$!

# Instead of "wait" which could make the script exit, use an infinite loop
echo "Railway startup script is now running continuously"
while true; do
  # Touch a file periodically to show activity
  touch /tmp/railway_script_alive
  sleep 60
done
