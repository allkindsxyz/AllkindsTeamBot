#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import requests
import ssl
from pathlib import Path
from dotenv import load_dotenv

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

# Run database migrations
print("Running database migrations...")
try:
    migration_result = subprocess.run(
        [sys.executable, "run_communicator_migrations.py"],
        capture_output=True,
        text=True,
        check=True
    )
    print(migration_result.stdout)
    if migration_result.returncode != 0:
        print(f"❌ Migration failed: {migration_result.stderr}")
        sys.exit(1)
    print("✅ Database migrations completed")
except subprocess.CalledProcessError as e:
    print(f"❌ Migration failed with error code {e.returncode}: {e.stderr}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Migration failed: {str(e)}")
    sys.exit(1)

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

# Kill any existing instances
try:
    # Get list of python processes
    ps_output = subprocess.check_output(["ps", "aux"], text=True)
    for line in ps_output.split('\n'):
        if ("src/communicator_bot/main.py" in line or "communicator_bot" in line) and "python" in line:
            # Extract PID (the second field in ps output)
            try:
                pid = line.split()[1]
                print(f"Killing existing communicator bot process: {pid}")
                try:
                    subprocess.run(["kill", "-9", pid], check=True)
                    print(f"Killed process {pid}")
                except subprocess.CalledProcessError:
                    print(f"Failed to kill process {pid}")
            except IndexError:
                pass

    # Make sure no processes are left
    time.sleep(1)  # Give the system time to clean up
    
except Exception as e:
    print(f"Error checking for existing processes: {e}")

# Start the bot in a new process
try:
    print("Starting new communicator bot instance...")
    # Use subprocess to start the bot and detach
    with open("communicator_bot_new.log", "a") as logfile:
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