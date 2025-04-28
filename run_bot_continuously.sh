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
start_health_server
start_health_checker() {
  log "Starting health check monitor"
  while true; do
    check_health || log "Warning: Health check failed"
    sleep 60
  done &
  HEALTH_CHECKER_PID=$!
  log "Health checker started with PID: $HEALTH_CHECKER_PID"
}

# Function to ensure environment variables are loaded
ensure_env_loaded() {
  # Check if .env file exists and load it
  if [ -f .env ]; then
    log "Loading environment variables from .env file"
    # Export all variables from .env file
    set -a
    source .env
    set +a
    log "Environment variables loaded from .env file"
  else
    log "No .env file found, using existing environment variables"
  fi
  
  # Check essential variables
  if [ -z "$BOT_TOKEN" ]; then
    log "ERROR: BOT_TOKEN is not set!"
    return 1
  fi
  
  # Ensure USE_WEBHOOK is properly set
  if [ -z "$USE_WEBHOOK" ]; then
    log "USE_WEBHOOK not set, defaulting to 'false'"
    export USE_WEBHOOK="false"
  fi
  
  # Display key environment variables
  log "BOT_TOKEN: ${BOT_TOKEN:0:6}...${BOT_TOKEN: -6} (masked)"
  log "USE_WEBHOOK: $USE_WEBHOOK"
  log "DATABASE_URL: ${DATABASE_URL:-sqlite+aiosqlite:///./allkinds.db}"
  
  return 0
}

# Display environment information
log "=== ENVIRONMENT INFORMATION ==="
log "Hostname: $(hostname)"
log "Railway environment: ${RAILWAY_ENVIRONMENT:-local}"
log "Railway service: ${RAILWAY_SERVICE_NAME:-unknown}"
log "Health check port: ${PORT}"
log "Working directory: $(pwd)"

# Load environment variables
ensure_env_loaded || { log "Failed to set up environment variables"; exit 1; }

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
  
  # Update USE_WEBHOOK to match environment
  export USE_WEBHOOK="true"
  log "Forcing USE_WEBHOOK=true in production mode"
else
  # For local development, delete webhook to use polling
  log "Development environment detected. Deleting webhook to use polling mode..."
  RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook?drop_pending_updates=true")
  log "Delete webhook response: ${RESPONSE}"
  
  # Update USE_WEBHOOK to match environment
  export USE_WEBHOOK="false"
  log "Forcing USE_WEBHOOK=false in development mode"
fi

# Validate database connection in production
if [[ "${RAILWAY_ENVIRONMENT}" == "production" ]]; then
  log "Validating database connection in production environment..."
  if [[ -z "${DATABASE_URL}" ]]; then
    log "ERROR: DATABASE_URL environment variable is not set!"
    log "Please set DATABASE_URL to the PostgreSQL connection string."
    exit 1
  fi
  
  if [[ ! "${DATABASE_URL}" =~ ^(postgresql|postgres) ]]; then
    log "ERROR: DATABASE_URL must be a PostgreSQL connection!"
    log "Current DATABASE_URL starts with: ${DATABASE_URL:0:15}..."
    exit 1
  fi
  
  log "DATABASE_URL validation passed (PostgreSQL connection detected)"
  
  # Test database connection using Python
  log "Testing database connection..."
  DB_TEST_RESULT=$(python3 -c "
import asyncio, sys
from sqlalchemy.ext.asyncio import create_async_engine
async def test_db():
  try:
    print('Testing PostgreSQL connection...')
    engine = create_async_engine('${DATABASE_URL}'.replace('postgres://', 'postgresql+asyncpg://'))
    async with engine.connect() as conn:
      result = await conn.execute('SELECT 1')
      return True
  except Exception as e:
    print(f'Database connection error: {e}')
    return False
if asyncio.run(test_db()):
  print('Database connection successful!')
  sys.exit(0)
else:
  print('Failed to connect to database')
  sys.exit(1)
" 2>&1)
  DB_TEST_EXIT=$?
  
  log "Database test result: ${DB_TEST_RESULT}"
  if [[ $DB_TEST_EXIT -ne 0 ]]; then
    log "ERROR: Failed to connect to PostgreSQL database!"
    exit 1
  fi
  
  log "PostgreSQL database connection verified"
else
  log "Running in development mode with local database"
  # Ensure DATABASE_URL is set to something sensible for local development
  if [[ -z "${DATABASE_URL}" ]]; then
    log "Setting default DATABASE_URL for development"
    export DATABASE_URL="sqlite+aiosqlite:///./allkinds.db"
  fi
fi

# Function to verify bot token
verify_bot_token() {
  log "Verifying bot token..."
  BOT_INFO=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getMe")
  if [[ "$BOT_INFO" =~ "\"ok\":true" ]]; then
    BOT_USERNAME=$(echo "$BOT_INFO" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
    BOT_ID=$(echo "$BOT_INFO" | grep -o '"id":[0-9]*' | cut -d':' -f2)
    log "Bot token valid for @$BOT_USERNAME (ID: $BOT_ID)"
    return 0
  else
    log "ERROR: Invalid bot token! Response: $BOT_INFO"
    return 1
  fi
}

# Verify the bot token before starting
verify_bot_token || { 
  log "Bot token verification failed. Please check your BOT_TOKEN environment variable."
  log "Waiting 60 seconds before retrying..."
  sleep 60
  verify_bot_token || {
    log "Bot token verification failed again. Exiting."
    exit 1
  }
}

# Start the bot

# Function to start the health server
start_health_server() {
  log "Starting health server on port ${PORT}..."
  python3 health_server.py &
  HEALTH_SERVER_PID=$!
  log "Health server started with PID: ${HEALTH_SERVER_PID}"
  
  # Verify health server is running
  sleep 2
  if ps -p ${HEALTH_SERVER_PID} > /dev/null; then
    log "Health server is running"
    return 0
  else
    log "WARNING: Health server failed to start!"
    return 1
  fi
}

run_bot() {
  log "Starting the bot process..."
  
  # Display key environment variables before starting
  log "Starting bot with BOT_TOKEN=${BOT_TOKEN:0:6}...${BOT_TOKEN: -6} (masked)"
  log "USE_WEBHOOK=${USE_WEBHOOK}"
  log "DATABASE_URL=${DATABASE_URL:-sqlite+aiosqlite:///./allkinds.db}"
  
  # Export USE_WEBHOOK explicitly based on environment
  if [[ "${RAILWAY_ENVIRONMENT}" == "production" && -n "${WEBHOOK_DOMAIN}" ]]; then
    export USE_WEBHOOK=true
    log "Running in webhook mode"
  else
    export USE_WEBHOOK=false
    log "Running in polling mode"
  fi
  
  # Run the bot with explicit environment variables
  BOT_TOKEN="${BOT_TOKEN}" \
  USE_WEBHOOK="${USE_WEBHOOK}" \
  DATABASE_URL="${DATABASE_URL}" \
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
start_health_server
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
    
    # Verify bot token after failures
    verify_bot_token || {
      log "Bot token appears to be invalid after failure. Verifying environment..."
      ensure_env_loaded
    }
    
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