#!/usr/bin/env python3
import os
import sys
import signal
import subprocess
import time
import psutil

# Constants
PID_FILE = "bot.pid"
LOCK_FILE = "bot.lock"
BOT_MODULE_PATTERNS = ["src.bot.main", "src/bot/main", "src.bot/main.py"]
# Add Poetry patterns
POETRY_PATTERNS = ["poetry run python -m src.bot.main", "poetry run python.*src.bot.main"]

print("\n===== ALLKINDS TELEGRAM BOT STOPPER =====\n")

# Read PID file if exists
pid_from_file = None
if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE, "r") as f:
            pid_from_file = int(f.read().strip())
        print(f"Found PID file with process ID: {pid_from_file}")
    except Exception as e:
        print(f"⚠️ Error reading PID file: {e}")

# Find all bot processes
print("Searching for bot processes...")
found_pids = []

# Method 1: Check the specific PID from file
if pid_from_file:
    try:
        if psutil.pid_exists(pid_from_file):
            proc = psutil.Process(pid_from_file)
            cmdline = ' '.join(proc.cmdline())
            if any(pattern in cmdline for pattern in BOT_MODULE_PATTERNS + POETRY_PATTERNS):
                found_pids.append(pid_from_file)
                print(f"✓ Verified process {pid_from_file} is our bot")
    except Exception as e:
        print(f"⚠️ Error checking PID {pid_from_file}: {e}")

# Method 2: Find all processes that match our patterns
try:
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] if proc.info['cmdline'] else [])
            # Check for both direct python patterns and poetry patterns
            if any(pattern in cmdline for pattern in BOT_MODULE_PATTERNS + POETRY_PATTERNS):
                pid = proc.info['pid']
                if pid not in found_pids:
                    found_pids.append(pid)
                    print(f"Found bot process: {pid}")
        except:
            continue
except Exception as e:
    print(f"⚠️ Error searching for processes: {e}")

# Method 3: Use system command to find processes
try:
    # Look for both Python and Poetry run processes
    cmd = "ps aux | grep -E '(python.*src.bot.main|poetry run.*src.bot.main)' | grep -v grep | awk '{print $2}'"
    output = subprocess.check_output(cmd, shell=True, text=True)
    for line in output.strip().split('\n'):
        if line.strip():
            try:
                pid = int(line.strip())
                if pid not in found_pids:
                    found_pids.append(pid)
                    print(f"Found bot process: {pid}")
            except:
                pass
except:
    pass

# Kill all found processes
if found_pids:
    print(f"\nTerminating {len(found_pids)} bot processes...")
    for pid in found_pids:
        try:
            # Try SIGTERM first
            print(f"Sending SIGTERM to process {pid}...")
            os.kill(pid, signal.SIGTERM)
            
            # Wait briefly
            time.sleep(0.5)
            
            # If still running, use SIGKILL
            if psutil.pid_exists(pid):
                print(f"Process {pid} still running, sending SIGKILL...")
                os.kill(pid, signal.SIGKILL)
                
            print(f"✓ Process {pid} terminated")
        except Exception as e:
            print(f"⚠️ Error killing process {pid}: {e}")
            # Try one more time with system command
            try:
                subprocess.run(f"kill -9 {pid}", shell=True)
            except:
                pass

    # Verify all processes are dead
    time.sleep(1)
    all_killed = True
    for pid in found_pids:
        if psutil.pid_exists(pid):
            try:
                proc = psutil.Process(pid)
                cmdline = ' '.join(proc.cmdline())
                if any(pattern in cmdline for pattern in BOT_MODULE_PATTERNS + POETRY_PATTERNS):
                    print(f"⚠️ Process {pid} is still running!")
                    all_killed = False
            except:
                pass
                
    if all_killed:
        print("\n✅ All bot processes successfully terminated")
    else:
        print("\n⚠️ Some processes could not be terminated")
else:
    print("\nNo bot processes found")

# Clean up files
try:
    if os.path.exists(PID_FILE):
        os.unlink(PID_FILE)
        print("✓ Removed PID file")
    
    if os.path.exists(LOCK_FILE):
        os.unlink(LOCK_FILE)
        print("✓ Removed lock file")
except Exception as e:
    print(f"⚠️ Error cleaning up files: {e}")

# Final forceful cleanup
try:
    subprocess.run("pkill -9 -f '(python.*src.bot.main|poetry run.*src.bot.main)'", shell=True)
except:
    pass

print("\nBot shutdown complete. To start the bot again, run: poetry run python start_bot.py") 