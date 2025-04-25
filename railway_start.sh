#!/bin/bash
set -e  # Exit on any error

echo "===== RAILWAY STARTUP SCRIPT ====="
echo "Railway environment:"
echo "RAILWAY_SERVICE_NAME: $RAILWAY_SERVICE_NAME"
echo "RAILWAY_ENVIRONMENT: $RAILWAY_ENVIRONMENT"
echo "PORT: $PORT"
echo "RAILWAY_PUBLIC_DOMAIN: $RAILWAY_PUBLIC_DOMAIN"
echo "RAILWAY_PUBLIC_URL: $RAILWAY_PUBLIC_URL"
echo "PYTHON VERSION: $(python --version)"

# Set environment variables
echo "Configuring environment..."
# WEBHOOK_DOMAIN is now set via Railway Variables if needed, or uses RAILWAY_PUBLIC_DOMAIN
# export WEBHOOK_DOMAIN="$RAILWAY_PUBLIC_URL" # Remove this potentially incorrect override
# export HEALTH_PORT=8080 # Remove health port export
echo "Using webhook domain: $WEBHOOK_DOMAIN" # This will reflect the value used by on_startup
# echo "Health check port: $HEALTH_PORT" # Remove health port log

# Function to check port availability
check_port_available() {
  local port=$1
  echo "Checking if port $port is available..."
  if nc -z 127.0.0.1 $port; then
    echo "WARNING: Port $port is already in use"
  else
    echo "Port $port is available"
  fi
}

# Check if the PORT environment variable exists and is valid
if [ -z "$PORT" ]; then
  echo "ERROR: PORT environment variable is not set"
  export PORT=8000
  echo "Using default port: $PORT"
fi

# Check if the port is available
check_port_available $PORT

echo "Checking database connection..."
# Print PostgreSQL version to verify connection
python3 -c "
import os, psycopg2, time
for i in range(5):
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        cur.execute('SELECT version()')
        print(f'Connected to PostgreSQL: {cur.fetchone()[0]}')
        conn.close()
        break
    except Exception as e:
        print(f'Database connection attempt {i+1}/5 failed: {e}')
        if i < 4:
            print('Retrying in 5 seconds...')
            time.sleep(5)
        else:
            print('Could not connect to database after 5 attempts')
            # Continue anyway - we'll handle DB issues in the app
"

# Function to cleanup when script exits
cleanup() {
  echo "Cleaning up..."
  # Remove health check PID cleanup
  # if [ -n "$HEALTH_PID" ]; then
  #   echo "Killing health check server (PID: $HEALTH_PID)..."
  #   kill $HEALTH_PID 2>/dev/null || true
  # fi
  echo "Cleanup complete"
}

# Register the cleanup function
trap cleanup EXIT INT TERM

echo "Script finished. Application start is now handled by railway.toml startCommand."
# The actual python process is started by the startCommand in railway.toml
