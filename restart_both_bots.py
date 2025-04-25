#!/usr/bin/env python3
import os
import sys
import subprocess
import time

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)  # Change to the bot directory

# Stop any running instances
print("===== ALLKINDS BOT SYSTEM RESTART =====\n")

print("Stopping both bots...")
try:
    # Stop main bot
    if os.path.exists("stop_bot.py"):
        subprocess.run([sys.executable, "stop_bot.py"], check=True)
    else:
        subprocess.run(["pkill", "-f", "src.bot.main"], check=False)
    
    # Stop communicator bot
    subprocess.run(["pkill", "-f", "src.communicator_bot.main"], check=False)
    
    # Give processes time to terminate
    time.sleep(1)
    
    print("✅ All bots stopped")
except Exception as e:
    print(f"⚠️ Error stopping bots: {e}")

# Start the main bot
print("\nStarting main bot...")
try:
    result = subprocess.run([sys.executable, "start_bot.py"], 
                           capture_output=True, 
                           text=True, 
                           check=True)
    # Print only essential output
    for line in result.stdout.split('\n'):
        if "✅" in line or "Bot started" in line or "Bot is running" in line:
            print(line)
    print("✅ Main bot started")
except Exception as e:
    print(f"⚠️ Error starting main bot: {e}")
    sys.exit(1)

# Start the communicator bot
print("\nStarting communicator bot...")
try:
    result = subprocess.run([sys.executable, "start_communicator_bot.py"], 
                           capture_output=True, 
                           text=True, 
                           check=True)
    # Print only essential output
    for line in result.stdout.split('\n'):
        if "✅" in line or "bot started" in line or "bot is running" in line:
            print(line)
    print("✅ Communicator bot started")
except Exception as e:
    print(f"⚠️ Error starting communicator bot: {e}")
    sys.exit(1)

print("\n✅ Both bots are running successfully!")
print("To stop the main bot, run: ./stop_bot.py")
print("To stop the communicator bot, run: pkill -f 'src.communicator_bot.main'")
print("To restart both bots, run this script again: ./restart_both_bots.py") 