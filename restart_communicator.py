#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import requests
import ssl
from pathlib import Path
from dotenv import load_dotenv

print("===== COMMUNICATOR BOT RESTART SCRIPT =====")

# First, aggressively kill any running communicator bot processes
print("Forcefully terminating all communicator bot instances...")
try:
    # Get our own PID to exclude it
    my_pid = os.getpid()
    print(f"Own PID: {my_pid} (will be excluded)")
    
    # Try pkill first but exclude our script pattern
    subprocess.run(["pkill", "-9", "-f", "src.communicator_bot.main"],
                  stderr=subprocess.PIPE, stdout=subprocess.PIPE, check=False)
    time.sleep(2)
    
    # Double-check no processes remain
    ps_output = subprocess.check_output(["ps", "aux"], text=True)
    for line in ps_output.split('\n'):
        if "communicator" in line.lower() and "python" in line.lower() and "grep" not in line and "restart_communicator.py" not in line:
            try:
                pid = int(line.split()[1])
                # Skip our own process
                if pid == my_pid:
                    print(f"Skipping own process: {pid}")
                    continue
                    
                print(f"Killing remaining process: {pid}")
                subprocess.run(["kill", "-9", str(pid)], check=False)
            except Exception as e:
                print(f"Error killing process: {e}")
    
    # Wait for processes to die
    time.sleep(2)
except Exception as e:
    print(f"Error during process cleanup: {e}")

# Load environment variables
load_dotenv()

script_dir = Path(__file__).parent.resolve()
os.chdir(script_dir)  # Change to the bot directory

# Get the bot token
COMMUNICATOR_BOT_TOKEN = os.getenv("COMMUNICATOR_BOT_TOKEN")
if not COMMUNICATOR_BOT_TOKEN:
    from src.core.config import get_settings
    settings = get_settings()
    COMMUNICATOR_BOT_TOKEN = settings.COMMUNICATOR_BOT_TOKEN

# Make sure we're in the correct directory
print(f"Starting communicator bot from {script_dir}")

# Reset the webhook to ensure clean start
print("Resetting Telegram webhook...")
try:
    # Disable SSL certificate verification for this request
    response = requests.get(
        f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true",
        verify=False
    )
    if response.status_code == 200 and response.json().get("ok"):
        print("✅ Webhook cleared successfully")
    else:
        print(f"⚠️ Failed to clear webhook: {response.text}")
except Exception as e:
    print(f"⚠️ Error clearing webhook: {e}")

# Start the bot in a new process
try:
    print("Starting new communicator bot instance...")
    # Use subprocess to start the bot and detach
    with open("communicator_bot.log", "a") as logfile:
        subprocess.Popen(
            [sys.executable, "-m", "src.communicator_bot.main"],
            stdout=logfile,
            stderr=logfile,
            start_new_session=True
        )
    print("Communicator bot started successfully!")
except Exception as e:
    print(f"Failed to start communicator bot: {e}")
    sys.exit(1)

print("Communicator bot is now running in the background")
print("===============================================") 