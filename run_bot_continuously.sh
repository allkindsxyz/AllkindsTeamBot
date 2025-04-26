#!/bin/bash

# Bot Runner Script (robust version)
# This script will keep the bot running continuously, restarting it if it crashes
# It also implements health checks and logs activity

# Health check endpoint port 
PORT=${PORT:-8080}

# Set up error handling and early exit
set -e

# Create logs directory if it doesn't exist
mkdir -p logs

# Log file
LOG_FILE="logs/bot_runner_$(date +%Y%m%d_%H%M%S).log"

# Function to log messages
log() {
  local message="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  echo "$message"
  echo "$message" >> "$LOG_FILE"
}

# Function to check if the health endpoint is responding
check_health() {
  if curl -s http://localhost:${PORT}/health > /dev/null; then
    log "Health check: OK"
    return 0
  else
    log "Health check: FAILED"
    return 1
  fi
}

# Function to run health check in a separate process
start_health_checker() {
  log "Starting health check monitor"
  while true; do
    check_health || log "Warning: Health check failed"
    sleep 60
  done &
  HEALTH_CHECKER_PID=$!
  log "Health checker started with PID: $HEALTH_CHECKER_PID"
}

# Display environment information
log "=== ENVIRONMENT INFORMATION ==="
log "Hostname: $(hostname)"
log "Railway environment: ${RAILWAY_ENVIRONMENT:-local}"
log "Railway service: ${RAILWAY_SERVICE_NAME:-unknown}"
log "Health check port: ${PORT}"
log "Bot token available: $(if [[ -n "${BOT_TOKEN}" ]]; then echo "YES"; else echo "NO"; fi)"
log "Working directory: $(pwd)"

# Set proper webhook in production, or reset in development
if [[ "${RAILWAY_ENVIRONMENT}" == "production" && -n "${WEBHOOK_DOMAIN}" ]]; then
  log "Setting up webhook for production environment"
  WEBHOOK_PATH=${WEBHOOK_PATH:-"/webhook"}
  WEBHOOK_URL="${WEBHOOK_DOMAIN}${WEBHOOK_PATH}"
  log "Setting webhook to: ${WEBHOOK_URL}"
  RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook?url=${WEBHOOK_URL}&drop_pending_updates=true")
  log "Webhook setup response: ${RESPONSE}"
  
  # Verify webhook is set correctly
  WEBHOOK_INFO=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo")
  log "Webhook info: ${WEBHOOK_INFO}"
else
  # For local development, delete webhook to use polling
  log "Development environment detected. Deleting webhook to use polling mode..."
  curl -s "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook?drop_pending_updates=true" > /dev/null
fi

# Start the bot
run_bot() {
  log "Starting the bot process..."
  
  # Export USE_WEBHOOK explicitly based on environment
  if [[ "${RAILWAY_ENVIRONMENT}" == "production" && -n "${WEBHOOK_DOMAIN}" ]]; then
    export USE_WEBHOOK=true
    log "Running in webhook mode"
  else
    export USE_WEBHOOK=false
    log "Running in polling mode"
  fi
  
  # Run the bot in the foreground
  python3 -m src.bot.main
  
  # Get the exit code
  local exit_code=$?
  
  if [ $exit_code -eq 0 ]; then
    log "Bot exited cleanly with code 0"
  else
    log "Bot exited with error code $exit_code"
  fi
  
  return $exit_code
}

# Main loop to keep the bot running
log "=== STARTING BOT RUNNER ==="
start_health_checker

# Keep track of consecutive failures
consecutive_failures=0
max_consecutive_failures=5

while true; do
  # Run the bot
  run_bot
  exit_code=$?
  
  # If the bot exited with an error
  if [ $exit_code -ne 0 ]; then
    consecutive_failures=$((consecutive_failures + 1))
    log "Consecutive failures: $consecutive_failures/$max_consecutive_failures"
    
    if [ $consecutive_failures -ge $max_consecutive_failures ]; then
      log "Too many consecutive failures. Sleeping for longer period before retry."
      sleep 300  # 5 minutes
      consecutive_failures=0
    else
      # Wait before restarting
      backoff_time=$((30 * consecutive_failures))
      log "Waiting $backoff_time seconds before restarting..."
      sleep $backoff_time
    fi
  else
    consecutive_failures=0
  fi
  
  log "Restarting the bot..."
done

# This point should never be reached 