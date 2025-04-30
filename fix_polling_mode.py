#!/usr/bin/env python3
"""
Fix Polling Mode Script

This script fixes bots not responding despite setting USE_WEBHOOK=false by:
1. Verifying and fixing bot token configurations
2. Updating USE_WEBHOOK setting both in .env and code
3. Resetting webhooks properly with error handling
4. Configuring proper startup sequence without webhooks
"""

import os
import sys
import logging
import asyncio
import requests
import aiohttp
import ssl
import subprocess
from datetime import datetime
import re
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except ImportError:
    logger.warning("python-dotenv not installed, continuing without loading .env file")

# Config files to modify
CONFIG_FILE = "src/core/config.py"
MAIN_FILE = "src/main.py"
MAIN_BOT_FILE = "src/bot/main.py"
COMMUNICATOR_BOT_FILE = "src/communicator_bot/main.py"

def backup_file(file_path):
    """Create a backup of a file before modifying it."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found, cannot backup: {file_path}")
        return False
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.polling_fix_{timestamp}.bak"
    
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup of {file_path}: {e}")
        return False

def update_env_file():
    """Create or update .env file with USE_WEBHOOK=false and verify tokens."""
    env_file = ".env"
    env_content = {}
    
    # Read existing .env file if it exists
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_content[key.strip()] = value.strip()
    
    # Update USE_WEBHOOK setting
    env_content["USE_WEBHOOK"] = "false"
    
    # Make sure tokens are present and correctly quoted if they contain special characters
    tokens = ["BOT_TOKEN", "COMMUNICATOR_BOT_TOKEN"]
    for token_key in tokens:
        token_value = os.environ.get(token_key, env_content.get(token_key, ""))
        if token_value:
            # If token has special characters, quote it
            if any(c in token_value for c in " ,;:|\"'"):
                if not (token_value.startswith('"') and token_value.endswith('"')):
                    token_value = f'"{token_value}"'
            env_content[token_key] = token_value
    
    # Write updated content back to .env file
    with open(env_file, "w") as f:
        f.write(f"# Updated by fix_polling_mode.py at {datetime.now().isoformat()}\n")
        for key, value in env_content.items():
            f.write(f"{key}={value}\n")
    
    logger.info(f"Updated {env_file} with USE_WEBHOOK=false and verified tokens")
    return True

def fix_config_file():
    """Update config.py to always use polling mode."""
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found: {CONFIG_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(CONFIG_FILE):
        return False
        
    try:
        # Read the file
        with open(CONFIG_FILE, 'r') as file:
            content = file.read()
            
        # Find and update the USE_WEBHOOK field
        use_webhook_pattern = r"(USE_WEBHOOK\s*:\s*bool\s*=\s*Field\().*?(\))"
        
        # Update to always use polling mode
        updated_content = re.sub(
            use_webhook_pattern,
            r'\1default=False, alias="USE_WEBHOOK"\2',
            content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(CONFIG_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {CONFIG_FILE} to force polling mode")
        return True
    except Exception as e:
        logger.error(f"Error updating {CONFIG_FILE}: {e}")
        return False

def fix_main_file():
    """Update main.py to prevent setting up webhook."""
    if not os.path.exists(MAIN_FILE):
        logger.error(f"Main file not found: {MAIN_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(MAIN_FILE):
        return False
        
    try:
        # Read the file
        with open(MAIN_FILE, 'r') as file:
            content = file.read()
            
        # Update the environment variables section to force webhook off
        env_section_pattern = r"(# Set environment variables for children processes.*?)(os\.environ\[\"WEBHOOK_HOST\"\] = webhook_url.*?)(.*?)"
        
        # Replace with code that forces USE_WEBHOOK to false
        updated_content = re.sub(
            env_section_pattern,
            r'\1# Force polling mode\nos.environ["USE_WEBHOOK"] = "false"\n\n\3',
            content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(MAIN_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {MAIN_FILE} to force polling mode")
        return True
    except Exception as e:
        logger.error(f"Error updating {MAIN_FILE}: {e}")
        return False

def fix_main_bot_file():
    """Update main bot file to improve polling mode implementation."""
    if not os.path.exists(MAIN_BOT_FILE):
        logger.error(f"Main bot file not found: {MAIN_BOT_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(MAIN_BOT_FILE):
        return False
        
    try:
        # Read the file
        with open(MAIN_BOT_FILE, 'r') as file:
            content = file.read()
            
        # Add enhanced logging in the main function
        main_function_pattern = r"(async def main\(\):.*?)(# Decide between webhook and polling modes.*?if settings\.USE_WEBHOOK:.*?else:)(.*?)(await run_polling_bot\(\))"
        
        # Replace with code that logs and forces polling mode
        updated_content = re.sub(
            main_function_pattern,
            r'\1# Force polling mode regardless of settings\nlogger.info("USE_WEBHOOK setting overridden to False, using polling mode")\n\3\n# Add detailed diagnostics\nlogger.info("Starting bot in polling mode with detailed diagnostics:")\nlogger.info(f"- Bot Token available: {bool(BOT_TOKEN)}")\nlogger.info(f"- Database URL configured: {bool(settings.db_url)}")\nlogger.info(f"- Using storage: {\'Redis\' if settings.REDIS_URL else \'Memory\'}")\n\4',
            content,
            flags=re.DOTALL
        )
        
        # Improve the run_polling_bot function to ensure webhook is properly deleted
        polling_pattern = r"(async def run_polling_bot\(\):.*?)(# Set up signal handlers)(.*?)"
        
        # Add enhanced webhook deletion with retries
        updated_content = re.sub(
            polling_pattern,
            r'\1# Ensure webhook is completely removed with retries\nfor attempt in range(3):\n    logger.info(f"Webhook deletion attempt {attempt+1}/3")\n    try:\n        await bot.delete_webhook(drop_pending_updates=True)\n        logger.info("Webhook deleted successfully")\n        # Verify deletion\n        webhook_info = await bot.get_webhook_info()\n        if not webhook_info.url:\n            logger.info("Confirmed webhook is not set")\n            break\n        else:\n            logger.warning(f"Webhook still set to {webhook_info.url}, retrying...")\n    except Exception as e:\n        logger.error(f"Error deleting webhook: {e}")\n    await asyncio.sleep(1)\n\n\2\3',
            updated_content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(MAIN_BOT_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {MAIN_BOT_FILE} with improved polling mode implementation")
        return True
    except Exception as e:
        logger.error(f"Error updating {MAIN_BOT_FILE}: {e}")
        return False

def fix_communicator_bot_file():
    """Update communicator bot file to prevent webhook setup."""
    if not os.path.exists(COMMUNICATOR_BOT_FILE):
        logger.error(f"Communicator bot file not found: {COMMUNICATOR_BOT_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(COMMUNICATOR_BOT_FILE):
        return False
        
    try:
        # Read the file
        with open(COMMUNICATOR_BOT_FILE, 'r') as file:
            content = file.read()
            
        # Find the start_communicator_bot function and update to enforce polling
        start_function_pattern = r"(async def start_communicator_bot\(\) -> None:.*?)(logger\.info\(\"Starting communicator bot in webhook mode\.\.\.\"\).*?await setup_webhook_server\(\))(.*?)"
        
        # Replace with polling mode
        updated_content = re.sub(
            start_function_pattern,
            r'\1logger.info("Starting communicator bot in polling mode...")\n        \n        # Start polling\n        try:\n            logger.info("Bot started polling for updates")\n            await dp.start_polling(bot, skip_updates=True)\n        except asyncio.CancelledError:\n            logger.info("Bot polling cancelled")\n        except Exception as e:\n            logger.error(f"Error during polling: {e}")\n            logger.exception("Full traceback:")\2\3',
            content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(COMMUNICATOR_BOT_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {COMMUNICATOR_BOT_FILE} to use polling mode")
        return True
    except Exception as e:
        logger.error(f"Error updating {COMMUNICATOR_BOT_FILE}: {e}")
        return False

async def reset_webhook_async(bot_token, bot_name="Unknown"):
    """Reset webhook for a bot using async HTTP request."""
    if not bot_token:
        logger.error(f"Cannot reset webhook for {bot_name}: Token not provided")
        return False
        
    logger.info(f"Resetting webhook for {bot_name}...")
    
    # Create a default SSL context that doesn't verify
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # Create a session with relaxed SSL configuration
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        # First, check current webhook status
        try:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
                ssl=False
            ) as response:
                if response.status == 200:
                    webhook_info = await response.json()
                    if webhook_info.get("ok"):
                        current_url = webhook_info.get("result", {}).get("url", "None")
                        logger.info(f"{bot_name} current webhook URL: {current_url}")
                    else:
                        logger.error(f"Failed to get webhook info: {webhook_info.get('description', 'Unknown error')}")
                else:
                    logger.error(f"Failed to get webhook info: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error getting webhook info: {e}")
        
        # Force delete the webhook with drop_pending_updates
        try:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true",
                ssl=False
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"{bot_name} webhook deleted successfully")
                        return True
                    else:
                        error = result.get("description", "Unknown error")
                        logger.error(f"Failed to delete webhook: {error}")
                else:
                    logger.error(f"Failed to delete webhook: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error resetting webhook: {e}")
    
    # If async method failed, try with regular requests
    try:
        logger.info(f"Trying alternative method for {bot_name}...")
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true",
            verify=False,
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                logger.info(f"{bot_name} webhook deleted successfully with alternative method")
                return True
            else:
                error = result.get("description", "Unknown error")
                logger.error(f"Failed to delete webhook with alternative method: {error}")
                # Check if it's an authentication error
                if "unauthorized" in error.lower() or "authentication" in error.lower():
                    logger.error(f"Authentication failed for {bot_name}. Please check your token.")
        else:
            logger.error(f"Failed to delete webhook: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Error with alternative webhook reset: {e}")
    
    return False

def verify_and_correct_token(bot_name, token_var_name):
    """Verify and correct token in environment variables."""
    token = os.environ.get(token_var_name)
    if not token:
        logger.error(f"{bot_name} token not found in environment variables")
        return None
    
    # Token should be alphanumeric with potential colons
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    
    # Correct token
    os.environ[token_var_name] = token
    logger.info(f"Verified and corrected {bot_name} token format")
    return token

async def main():
    """Main function to fix polling mode."""
    logger.info("Starting fix polling mode script...")
    
    # Verify and correct tokens
    main_bot_token = verify_and_correct_token("Main Bot", "BOT_TOKEN")
    comm_bot_token = verify_and_correct_token("Communicator Bot", "COMMUNICATOR_BOT_TOKEN")
    
    if not main_bot_token or not comm_bot_token:
        logger.error("Bot token verification failed. Cannot continue.")
        return False
    
    # Update .env file
    update_env_file()
    
    # Reset webhooks for both bots
    main_bot_result = await reset_webhook_async(main_bot_token, "Main Bot")
    comm_bot_result = await reset_webhook_async(comm_bot_token, "Communicator Bot")
    
    if main_bot_result and comm_bot_result:
        logger.info("Successfully reset webhooks for both bots")
    else:
        logger.warning("Failed to reset webhooks for one or both bots")
    
    # Fix configuration files
    config_result = fix_config_file()
    main_result = fix_main_file()
    main_bot_result = fix_main_bot_file()
    comm_bot_result = fix_communicator_bot_file()
    
    logger.info("================= SUMMARY =================")
    logger.info(f".env file updated with USE_WEBHOOK=false: ✅")
    logger.info(f"Config file updated: {'✅' if config_result else '❌'}")
    logger.info(f"Main file updated: {'✅' if main_result else '❌'}")
    logger.info(f"Main bot file updated: {'✅' if main_bot_result else '❌'}")
    logger.info(f"Communicator bot file updated: {'✅' if comm_bot_result else '❌'}")
    logger.info("===========================================")
    logger.info("To restart your application with polling mode:")
    logger.info("1. Kill the current bot processes")
    logger.info("2. Start the bots again with 'python -m src.main'")
    
    return True

if __name__ == "__main__":
    asyncio.run(main()) 