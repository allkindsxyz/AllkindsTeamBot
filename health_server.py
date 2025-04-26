import http.server
import socketserver
import os
import subprocess
import time

PORT = int(os.environ.get("PORT", 8080))

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running")
        elif self.path == "/status":
            # Get bot process status
            try:
                output = subprocess.check_output("ps aux | grep python3", shell=True).decode('utf-8')
                bot_status = "Bot processes:\n" + output
            except Exception as e:
                bot_status = f"Error getting bot status: {str(e)}"
                
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(bot_status.encode('utf-8'))
        elif self.path == "/logs":
            # Get last 50 lines of bot logs
            try:
                if os.path.exists("bot.log"):
                    with open("bot.log", "r") as f:
                        logs = f.readlines()
                        logs = logs[-50:] if len(logs) > 50 else logs
                        log_content = "Last 50 lines of bot.log:\n" + "".join(logs)
                else:
                    log_content = "Bot log file does not exist yet"
            except Exception as e:
                log_content = f"Error getting bot logs: {str(e)}"
                
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(log_content.encode('utf-8'))
        elif self.path == "/restart":
            # Restart the bot process
            try:
                subprocess.run("pkill -f 'python3 -m src.bot.main'", shell=True)
                time.sleep(2)
                subprocess.Popen("nohup python3 -m src.bot.main > bot.log 2>&1 &", shell=True)
                restart_response = "Bot restarted successfully"
            except Exception as e:
                restart_response = f"Error restarting bot: {str(e)}"
                
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(restart_response.encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found. Available endpoints: /health, /status, /logs, /restart")

print(f"Starting health check server on port {PORT}")
print(f"Available endpoints:")
print(f"  - /health: Basic health check")
print(f"  - /status: Show bot processes")
print(f"  - /logs: Show last 50 lines of bot logs")
print(f"  - /restart: Restart the bot process")

with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
    print(f"Health check server running at http://localhost:{PORT}")
    httpd.serve_forever() 