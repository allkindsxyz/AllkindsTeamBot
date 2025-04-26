#!/bin/bash
# Script to run the bot and keep the container alive

set -e

# Display some info
echo "Starting bot process at $(date)"
echo "Current directory: $(pwd)"
echo "Environment: RAILWAY_ENVIRONMENT=${RAILWAY_ENVIRONMENT}"
echo "WEBHOOK_DOMAIN: ${WEBHOOK_DOMAIN}"
echo "RAILWAY_PUBLIC_DOMAIN: ${RAILWAY_PUBLIC_DOMAIN}"
echo "PORT: ${PORT}"

# Make prepare_env script executable and run it first if it exists
if [ -f "/app/prepare_env.sh" ]; then
  echo "Running prepare_env.sh script first..."
  chmod +x /app/prepare_env.sh
  /app/prepare_env.sh echo "Environment prepared"
fi

# Fix asyncpg installation before starting the bot
if [ -f "/app/pip_install_asyncpg.sh" ]; then
  echo "Running asyncpg installation fix..."
  chmod +x /app/pip_install_asyncpg.sh
  /app/pip_install_asyncpg.sh
  echo "Asyncpg installation fixed."
fi

# Wait a bit before starting the bot
echo "Waiting 5 seconds before starting the bot..."
sleep 5

# Create a simple health check server
cat > health_server.py << 'EOF'
import http.server
import socketserver
import os

PORT = int(os.environ.get("PORT", 8080))

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running")
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")

print(f"Starting health check server on port {PORT}")
with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
    print(f"Health check server running at http://localhost:{PORT}")
    httpd.serve_forever()
EOF

# Start the bot process in the background
echo "Starting bot in polling mode with: python3 -m src.bot.main"
nohup python3 -m src.bot.main > bot.log 2>&1 &
BOT_PID=$!
echo "Bot started with PID: $BOT_PID"

# Start the health check server
echo "Starting health check server to keep the container active"
python3 health_server.py 