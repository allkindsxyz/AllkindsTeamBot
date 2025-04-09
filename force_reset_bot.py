#!/usr/bin/env python3
import asyncio
import aiohttp
import ssl
import json
import time
import random
import logging
import os
import signal
import sys
from src.core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get bot tokens from settings
settings = get_settings()
MAIN_BOT_TOKEN = settings.BOT_TOKEN
COMMUNICATOR_BOT_TOKEN = settings.COMMUNICATOR_BOT_TOKEN

async def perform_request(url):
    """Perform HTTP request with SSL verification disabled."""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, timeout=10) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Error in HTTP request: {e}")
            return {"ok": False, "error": str(e)}

async def kill_existing_processes():
    """Kill any existing bot processes."""
    logger.info("Killing any existing bot processes...")
    try:
        os.system("pkill -f 'python3 -m src.bot.main' || true")
        os.system("pkill -f 'python3 -m src.communicator_bot.main' || true")
        await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"Error killing processes: {e}")

async def delete_webhook(token):
    """Delete webhook and drop pending updates."""
    logger.info(f"Deleting webhook for bot {token[-10:]}...")
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
    result = await perform_request(url)
    logger.info(f"Delete webhook result: {result}")
    return result

async def get_updates_with_offset(token, offset, timeout=1):
    """Get updates with specific offset to close existing sessions."""
    logger.info(f"Getting updates with offset {offset} for bot {token[-10:]}...")
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout={timeout}"
    result = await perform_request(url)
    logger.info(f"Get updates result: {json.dumps(result)[:100]}...")
    return result

async def get_webhook_info(token):
    """Get current webhook info."""
    logger.info(f"Getting webhook info for bot {token[-10:]}...")
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    result = await perform_request(url)
    logger.info(f"Webhook info: {result}")
    return result

async def advanced_reset(token):
    """More advanced method to reset bot connections."""
    # First delete webhook
    await delete_webhook(token)
    
    # Then try multiple offsets to force close any existing getUpdates session
    offsets = [-1, 1, 100, 999999999]
    for offset in offsets:
        await get_updates_with_offset(token, offset)
        # Add a random delay between requests
        await asyncio.sleep(random.uniform(1.0, 2.0))
    
    # Use increasing offsets to try to force old sessions to close
    for i in range(10):
        offset = random.randint(10000, 9999999)
        await get_updates_with_offset(token, offset)
        await asyncio.sleep(random.uniform(0.5, 1.5))
    
    # Final check with webhook info
    await get_webhook_info(token)
    
    logger.info("Advanced reset completed. Waiting before starting bot...")
    await asyncio.sleep(5)

async def main():
    # Kill any existing processes
    await kill_existing_processes()
    
    # Reset the main bot
    logger.info("Starting advanced reset for main bot...")
    await advanced_reset(MAIN_BOT_TOKEN)
    
    # Reset the communicator bot
    logger.info("Starting advanced reset for communicator bot...")
    await advanced_reset(COMMUNICATOR_BOT_TOKEN)
    
    logger.info("All resets completed. You can now try to start the bots manually.")
    
    # Option to start bots automatically
    start_bots = input("Do you want to start the bots now? (y/n): ").strip().lower()
    if start_bots == 'y':
        which_bot = input("Which bot to start? (main/communicator/both): ").strip().lower()
        
        if which_bot in ['main', 'both']:
            logger.info("Starting main bot...")
            os.system("python3 -m src.bot.main > main_bot.log 2>&1 &")
            logger.info("Main bot started. Check main_bot.log for output.")
        
        if which_bot in ['communicator', 'both']:
            logger.info("Starting communicator bot...")
            os.system("python3 -m src.communicator_bot.main > communicator_bot.log 2>&1 &")
            logger.info("Communicator bot started. Check communicator_bot.log for output.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
        sys.exit(0) 