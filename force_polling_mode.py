#!/usr/bin/env python3
"""
Force Polling Mode Script

This script ensures only one instance of the bot is running in polling mode.
It will:
1. Kill any existing bot processes
2. Delete the webhook
3. Run the bot in polling mode with extensive debugging
"""

import os
import sys
import signal
import subprocess
import time
import json
import requests
import logging
import psutil
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'logs/force_polling_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)

logger = logging.getLogger(__name__)

def find_and_kill_bot_processes():
    """Find and kill any existing bot processes."""
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check for bot processes
            if proc.info['cmdline'] and any('src.bot.main' in cmd for cmd in proc.info['cmdline']):
                if proc.pid != os.getpid():  # Don't kill ourselves
                    logger.info(f"Killing bot process: {proc.pid}")
                    proc.kill()
                    killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return killed_count

def delete_webhook(bot_token):
    """Delete any existing webhook."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true"
        response = requests.get(url)
        data = response.json()
        
        if data.get('ok'):
            logger.info("Webhook deleted successfully")
        else:
            logger.error(f"Failed to delete webhook: {data}")
        
        # Also check webhook info
        info_url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
        info_response = requests.get(info_url)
        info_data = info_response.json()
        
        if info_data.get('ok'):
            logger.info(f"Webhook info: {json.dumps(info_data['result'], indent=2)}")
        
        return data.get('ok', False)
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
        return False

def run_bot_in_polling_mode():
    """Run the bot in polling mode with debugging enabled."""
    logger.info("Starting bot in polling mode")
    
    # Set environment variables
    env = os.environ.copy()
    env['USE_WEBHOOK'] = 'false'
    env['DEBUG_LEVEL'] = 'DEBUG'
    env['PYTHONUNBUFFERED'] = '1'
    
    cmd = [sys.executable, '-m', 'src.bot.main']
    
    try:
        # Run the bot and capture output
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        logger.info(f"Bot started with PID: {process.pid}")
        
        # Stream output in real-time
        for line in process.stdout:
            print(line, end='')
            if "START COMMAND TRIGGERED" in line:
                logger.info("DETECTED START COMMAND IN LOGS")
        
        # Wait for process to finish
        return_code = process.wait()
        logger.info(f"Bot exited with code: {return_code}")
        return return_code
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping bot")
        if 'process' in locals():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        return 1
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        return 1

def main():
    """Main entry point."""
    logger.info("=== STARTING FORCE POLLING MODE ===")
    
    # Check if lock file exists
    lock_path = Path('force_polling.lock')
    if lock_path.exists():
        pid = lock_path.read_text().strip()
        logger.warning(f"Lock file exists with PID: {pid}")
        try:
            # Check if process is still running
            pid = int(pid)
            if psutil.pid_exists(pid):
                logger.error(f"Another instance already running with PID: {pid}")
                return 1
            else:
                logger.info(f"Stale lock file found, removing")
                lock_path.unlink()
        except (ValueError, TypeError):
            logger.warning("Invalid PID in lock file, removing")
            lock_path.unlink()
    
    # Create lock file
    lock_path.write_text(str(os.getpid()))
    
    try:
        # Step 1: Kill any existing bot processes
        killed = find_and_kill_bot_processes()
        logger.info(f"Killed {killed} existing bot processes")
        
        # Step 2: Delete webhook
        bot_token = os.environ.get('BOT_TOKEN')
        if not bot_token:
            logger.error("BOT_TOKEN environment variable not set")
            return 1
        
        success = delete_webhook(bot_token)
        if not success:
            logger.warning("Failed to delete webhook, continuing anyway")
        
        # Wait a bit for webhook to be fully cleared
        logger.info("Waiting 3 seconds for webhook to clear...")
        time.sleep(3)
        
        # Step 3: Run bot in polling mode
        return_code = run_bot_in_polling_mode()
        
        return return_code
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    finally:
        # Clean up lock file
        if lock_path.exists():
            lock_path.unlink()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1) 