#!/usr/bin/env python3
"""
Reset script for Communicator Bot - Handles token refresh
"""
import asyncio
import json
import random
import aiohttp
import time
import logging
import os
import signal
import sys
import ssl
from src.core.config import get_settings
from dotenv import load_dotenv

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# SSL context that ignores verification for debugging
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Load token from environment for standalone usage
def get_token():
    """Get communicator bot token from environment or settings"""
    # Try direct env vars first
    load_dotenv()
    token = os.getenv("COMMUNICATOR_BOT_TOKEN")
    
    # Fallback to settings
    if not token:
        settings = get_settings()
        token = settings.COMMUNICATOR_BOT_TOKEN
    
    return token

# Initialize token only when directly imported
COMMUNICATOR_BOT_TOKEN = get_token()

async def kill_processes():
    """Kill any existing bot processes"""
    logger.info("Killing any existing bot processes...")
    # Platform-agnostic process kill based on grep for bot scripts
    try:
        # Kill any python processes running the communicator bot
        os.system("pkill -f 'python.*communicator_bot'")
        time.sleep(2)  # Give processes time to die
    except Exception as e:
        logger.warning(f"Error trying to kill processes: {e}")

async def delete_webhook(token=None):
    """Delete any existing webhooks"""
    if token is None:
        token = COMMUNICATOR_BOT_TOKEN
    
    logger.info(f"Deleting webhook for bot {token[:8]}...")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        async with session.get(url) as response:
            result = await response.json()
            logger.info(f"Delete webhook result: {result}")
            return result

async def get_webhook_info(token=None):
    """Get webhook info to verify it's deleted"""
    if token is None:
        token = COMMUNICATOR_BOT_TOKEN
        
    logger.info(f"Getting webhook info for bot {token[:8]}...")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        async with session.get(url) as response:
            result = await response.json()
            logger.info(f"Webhook info: {result}")
            return result

async def get_updates_with_offset(token=None, offset=-1):
    """Force reset pending updates with different offsets"""
    if token is None:
        token = COMMUNICATOR_BOT_TOKEN
        
    logger.info(f"Getting updates with offset {offset} for bot {token[:8]}...")
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&limit=1&timeout=1"
            async with session.get(url) as response:
                result = await response.json()
                logger.info(f"Get updates result: {str(result)[:100]}...")
                return result
    except asyncio.TimeoutError:
        logger.warning("Timeout when getting updates - this is actually good, means no conflict")
        return {"ok": True, "result": []}
    except Exception as e:
        logger.error(f"Error getting updates: {e}")
        return None

async def reset_bot(token=None):
    """Main function to reset the bot"""
    if token is None:
        token = COMMUNICATOR_BOT_TOKEN
        
    try:
        # First kill any existing bot processes
        await kill_processes()
        
        # Delete webhook
        result = await delete_webhook(token)
        if not result or not result.get('ok'):
            if result and result.get('error_code') == 401:
                logger.error("Unauthorized - token is invalid! Please check your .env file and ensure COMMUNICATOR_BOT_TOKEN is correct.")
                return False
            
        # Force clear pending updates with different offset strategies
        offsets = [-1, 1, 100]
        # Add 10 random large offsets to ensure we clear out any stuck messages
        offsets.extend([random.randint(1000000, 9999999) for _ in range(10)])
        
        for offset in offsets:
            result = await get_updates_with_offset(token, offset)
            # Add random delay to avoid rate limits
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
        # Final check on webhook info
        await get_webhook_info(token)
        
        logger.info("Communicator bot reset completed. Waiting before starting bot...")
        await asyncio.sleep(5)
        return True
        
    except Exception as e:
        logger.exception(f"Error during reset: {e}")
        return False

async def verify_token(token=None):
    """Verify the token is valid by making a simple call to getMe API"""
    if token is None:
        token = COMMUNICATOR_BOT_TOKEN
        
    logger.info("Verifying communicator bot token...")
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            url = f"https://api.telegram.org/bot{token}/getMe"
            async with session.get(url) as response:
                result = await response.json()
                if result.get('ok'):
                    bot_info = result.get('result', {})
                    bot_username = bot_info.get('username', 'Unknown')
                    logger.info(f"Token is valid for bot: @{bot_username}")
                    return True
                else:
                    logger.error(f"Invalid token: {result}")
                    return False
    except Exception as e:
        logger.exception(f"Error verifying token: {e}")
        return False

def signal_handler(sig, frame):
    """Handle Ctrl+C interruption"""
    logger.info("Process interrupted by user.")
    sys.exit(0)

async def main():
    """Main entry point when run as a standalone script"""
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # First verify the token is valid
    if not await verify_token():
        logger.error("Token verification failed. Please check your COMMUNICATOR_BOT_TOKEN environment variable.")
        return
    
    # Then reset the bot
    success = await reset_bot()
    if success:
        logger.info("Bot reset successful. You can now start the communicator bot.")
    else:
        logger.error("Bot reset failed. Please check the logs for details.")

if __name__ == "__main__":
    # When run directly as a script
    asyncio.run(main()) 