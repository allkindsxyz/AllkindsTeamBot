#!/usr/bin/env python3
"""
Force Polling Mode Script

This script forces both bots to use polling mode by:
1. Directly setting USE_WEBHOOK=false in the environment
2. Actively deleting any configured webhooks
3. Creating/updating a .env file with the correct settings
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except ImportError:
    logger.warning("python-dotenv not installed, continuing without loading .env file")

# Get tokens from environment
MAIN_BOT_TOKEN = os.environ.get("BOT_TOKEN")
COMMUNICATOR_BOT_TOKEN = os.environ.get("COMMUNICATOR_BOT_TOKEN")

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
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
            ) as response:
                if response.status == 200:
                    webhook_info = await response.json()
                    if webhook_info.get("ok"):
                        current_url = webhook_info.get("result", {}).get("url", "None")
                        logger.info(f"{bot_name} current webhook URL: {current_url}")
                else:
                    logger.error(f"Failed to get webhook info: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error getting webhook info: {e}")
        
        # Force delete the webhook with drop_pending_updates
        try:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true"
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
        else:
            logger.error(f"Failed to delete webhook: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Error with alternative webhook reset: {e}")
    
    return False

def update_env_file():
    """Create or update .env file with USE_WEBHOOK=false."""
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
    
    # Write updated content back to .env file
    with open(env_file, "w") as f:
        f.write(f"# Updated by force_polling_mode.py at {datetime.now().isoformat()}\n")
        for key, value in env_content.items():
            f.write(f"{key}={value}\n")
    
    logger.info(f"Updated {env_file} with USE_WEBHOOK=false")
    return True

def verify_environment_vars():
    """Verify that essential environment variables are set."""
    required_vars = ["BOT_TOKEN", "COMMUNICATOR_BOT_TOKEN"]
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these variables in your .env file or environment before running this script")
        return False
    
    logger.info("All required environment variables are set")
    return True

def set_environment_var():
    """Directly set USE_WEBHOOK=false in the environment."""
    os.environ["USE_WEBHOOK"] = "false"
    logger.info("Set USE_WEBHOOK=false in the current environment")
    return True

async def main():
    """Main function to force polling mode."""
    logger.info("Starting force polling mode script...")
    
    # Verify environment variables
    if not verify_environment_vars():
        logger.error("Environment verification failed. Cannot continue.")
        return False
    
    # Set the variable in the current environment
    set_environment_var()
    
    # Update .env file
    update_env_file()
    
    # Reset webhooks for both bots
    main_bot_result = await reset_webhook_async(MAIN_BOT_TOKEN, "Main Bot")
    comm_bot_result = await reset_webhook_async(COMMUNICATOR_BOT_TOKEN, "Communicator Bot")
    
    if main_bot_result and comm_bot_result:
        logger.info("Successfully reset webhooks for both bots")
    else:
        logger.warning("Failed to reset webhooks for one or both bots")
    
    logger.info("================= SUMMARY =================")
    logger.info("USE_WEBHOOK=false set in environment: ✅")
    logger.info(f".env file updated with USE_WEBHOOK=false: ✅")
    logger.info(f"Main Bot webhook reset: {'✅' if main_bot_result else '❌'}")
    logger.info(f"Communicator Bot webhook reset: {'✅' if comm_bot_result else '❌'}")
    logger.info("===========================================")
    logger.info("To restart your application with polling mode:")
    logger.info("1. Kill the current bot processes")
    logger.info("2. Start the bots again with 'python -m src.main'")
    
    return True

if __name__ == "__main__":
    asyncio.run(main()) 