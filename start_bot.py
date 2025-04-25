#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess
import psutil
import logging
import requests
import atexit
import fcntl
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

LOCK_FILE = "bot.lock"
PID_FILE = "bot.pid"
BOT_SCRIPT = "src.bot.main"
BOT_MODULE_PATTERNS = ["src.bot.main", "src/bot/main", "src.bot/main.py"]

def is_file_locked(filepath):
    """Check if a file is locked by another process."""
    if not os.path.exists(filepath):
        return False
        
    try:
        with open(filepath, 'r') as f:
            try:
                # Try to get an exclusive lock without blocking
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # If we got here, the file wasn't locked
                fcntl.flock(f, fcntl.LOCK_UN)
                return False
            except IOError:
                # File is locked by another process
                return True
    except Exception:
        return False

def acquire_lock():
    """Create and lock a file to ensure only one instance runs."""
    try:
        if os.path.exists(LOCK_FILE):
            # Read existing PID
            try:
                with open(PID_FILE, 'r') as f:
                    pid = int(f.read().strip())
                
                # Check if process is running
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    cmdline = ' '.join(p.cmdline())
                    if any(pattern in cmdline for pattern in BOT_MODULE_PATTERNS):
                        print(f"Bot is already running with PID {pid}")
                        sys.exit(1)
            except:
                pass
                
        # Create new lock file
        with open(LOCK_FILE, 'w') as f:
            # Get an exclusive lock
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # If we got here, we have the lock
            f.write(str(os.getpid()))
            f.flush()
            
            # Register cleanup on exit
            def release_lock():
                try:
                    if os.path.exists(LOCK_FILE):
                        os.unlink(LOCK_FILE)
                except:
                    pass
                    
            atexit.register(release_lock)
            return True
    except IOError:
        print("Another instance is already running and has the lock")
        sys.exit(1)
    except Exception as e:
        print(f"Lock error: {e}")
        sys.exit(1)

def kill_all_bot_processes():
    """Kill all Telegram bot processes."""
    print("Terminating any existing bot processes...")
    current_pid = os.getpid()
    killed_count = 0
    found_pids = []
    
    # Get a list of all PIDs to kill
    try:
        # First using psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Skip current process
                if proc.info['pid'] == current_pid:
                    continue
                
                # Check if it's a Python process
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = ' '.join(proc.info['cmdline'] if proc.info['cmdline'] else [])
                    
                    # If it's our bot process
                    if any(pattern in cmdline for pattern in BOT_MODULE_PATTERNS):
                        found_pids.append(proc.info['pid'])
            except:
                continue
                
        # Second using system commands
        ps_cmd = "ps aux | grep -E 'python.*src.bot.main' | grep -v grep | awk '{print $2}'"
        output = subprocess.check_output(ps_cmd, shell=True, text=True)
        for line in output.strip().split('\n'):
            if line.strip():
                try:
                    pid = int(line.strip())
                    if pid != current_pid and pid not in found_pids:
                        found_pids.append(pid)
                except:
                    pass
    except Exception as e:
        print(f"Error finding processes: {e}")
    
    # Now kill all found processes
    for pid in found_pids:
        try:
            print(f"Terminating process {pid}...")
            try:
                # Try SIGTERM first
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                
                # If still running, use SIGKILL
                if psutil.pid_exists(pid):
                    os.kill(pid, signal.SIGKILL)
            except:
                # If SIGTERM fails, go directly to SIGKILL
                os.kill(pid, signal.SIGKILL)
                
            killed_count += 1
        except:
            continue
    
    # Final verification - make absolutely sure everything is killed
    pkill_cmd = "pkill -f -9 'python.*src.bot.main'"
    subprocess.run(pkill_cmd, shell=True, stderr=subprocess.DEVNULL)
    
    # Give processes time to die
    time.sleep(1)
    
    print(f"Terminated {killed_count} bot processes")
    return killed_count

def reset_telegram_webhook():
    """Reset the Telegram webhook and verify it's gone."""
    print("\nResetting Telegram webhook...")
    
    # Get the bot token
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        print("ERROR: BOT_TOKEN environment variable not set!")
        sys.exit(1)
    
    try:
        # Delete webhook with drop_pending_updates
        delete_url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        response = requests.post(
            delete_url,
            params={"drop_pending_updates": "true"}
        )
        
        if response.status_code == 200 and response.json().get("ok"):
            print("✅ Webhook cleared successfully")
        else:
            print(f"⚠️ Error clearing webhook: {response.text}")
            sys.exit(1)
            
        # Verify bot responds
        me_url = f"https://api.telegram.org/bot{bot_token}/getMe"
        me_response = requests.get(me_url)
        
        if me_response.status_code == 200 and me_response.json().get("ok"):
            bot_name = me_response.json()["result"].get("username", "Unknown")
            print(f"✅ Bot API responding, username: {bot_name}")
        else:
            print(f"⚠️ Bot not responding: {me_response.text}")
            sys.exit(1)
            
        # Wait a moment for webhook to fully clear
        time.sleep(1)
        
    except Exception as e:
        print(f"⚠️ Error communicating with Telegram API: {e}")
        sys.exit(1)

def start_bot_process():
    """Start the bot as a managed subprocess."""
    print("\nStarting the bot...")
    
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    # Create a timestamped log file
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/bot_{timestamp}.log"
    
    # Setup environment
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    try:
        # Start the bot process using Poetry
        with open(log_file, "w") as f:
            process = subprocess.Popen(
                ["poetry", "run", "python", "-m", BOT_SCRIPT],
                env=env,
                stdout=f,
                stderr=f,
                start_new_session=True  # Detach from parent
            )
        
        # Wait a moment to see if it stays running
        time.sleep(3)
        
        if process.poll() is None:
            # Process is still running
            pid = process.pid
            
            # Save PID to file
            with open(PID_FILE, "w") as f:
                f.write(str(pid))
                
            print(f"✅ Bot started successfully with PID: {pid}")
            print(f"Logs are being written to: {log_file}")
            return True
        else:
            # Process exited quickly
            print("❌ Bot terminated immediately after starting!")
            print(f"Check logs at {log_file}")
            return False
            
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        return False

def verify_single_instance():
    """Verify that only one instance of the bot is running."""
    print("\nVerifying only one instance is running...")
    
    try:
        # Check if our bot is running
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
            
        # Count all running instances
        count = 0
        our_instance_running = False
        
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] if proc.info['cmdline'] else [])
                if any(pattern in cmdline for pattern in BOT_MODULE_PATTERNS):
                    count += 1
                    if proc.info['pid'] == pid:
                        our_instance_running = True
            except:
                continue
                
        if count > 1:
            print(f"⚠️ Found {count} bot instances running!")
            if our_instance_running:
                print("Our instance is among them.")
            else:
                print("Our instance is not found, but others are running.")
        elif count == 1 and our_instance_running:
            print("✅ Verified only our bot instance is running")
        elif count == 0:
            print("❌ No bot instances are running!")
            return False
        else:
            print("⚠️ Different bot instance is running, not ours!")
            return False
            
        return our_instance_running
        
    except Exception as e:
        print(f"❌ Error verifying instance: {e}")
        return False

def main():
    """Main execution flow."""
    print("\n===== ALLKINDS TELEGRAM BOT STARTER =====\n")
    
    # Acquire lock to ensure single instance of the starter
    acquire_lock()
    
    # Kill any existing bot processes
    kill_all_bot_processes()
    
    # Reset the Telegram webhook
    reset_telegram_webhook()
    
    # Start the bot
    if start_bot_process():
        # Verify single instance
        if verify_single_instance():
            print("\n✅ Bot is running successfully!")
            print("To stop the bot, run: ./stop_bot.py")
            return 0
        else:
            print("\n⚠️ Instance verification failed.")
            return 1
    else:
        print("\n❌ Failed to start bot.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 