#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
import time

print("===== ALLKINDS COMMUNICATOR BOT RESTARTER =====")

# Kill any existing communicator bot processes
try:
    ps_output = subprocess.check_output(["ps", "aux"]).decode('utf-8')
    for line in ps_output.split('\n'):
        if "src.communicator_bot.main" in line and "grep" not in line:
            pid = int(line.split()[1])
            print(f"Killing communicator bot process with PID: {pid}")
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception as e:
                print(f"Error killing process {pid}: {e}")
            
    print("✅ Terminated existing communicator bot processes")
except Exception as e:
    print(f"Error finding processes: {e}")

# Wait a moment for processes to terminate
time.sleep(1)

# Start the communicator bot
print("Starting the communicator bot...")
try:
    log_file = open("communicator_bot_new.log", "w")
    process = subprocess.Popen(
        ["python3", "-m", "src.communicator_bot.main"],
        stdout=log_file,
        stderr=log_file,
        start_new_session=True
    )
    print(f"✅ Communicator bot started with PID: {process.pid}")
except Exception as e:
    print(f"Error starting communicator bot: {e}")

print("\n✅ Communicator bot restart complete!") 