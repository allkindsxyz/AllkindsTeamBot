#!/usr/bin/env python3
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger
import asyncio
import os
import signal
import sys
import aiohttp
import ssl
from dotenv import load_dotenv
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Any, Awaitable, Callable, Dict
from datetime import datetime
import threading
from aiohttp import web

from src.communicator_bot.handlers import register_handlers
from src.core.config import get_settings
from src.communicator_bot.middlewares import DatabaseMiddleware, LoggingMiddleware, BotMiddleware

# Set up logging to a specific file for debugging
current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"logs/communicator_debug_{current_time}.log"
logger.remove()  # Remove default handlers
logger.add(log_file, rotation="20 MB", level="DEBUG", backtrace=True, diagnose=True)
logger.add(sys.stderr, level="INFO")
logger.info(f"Communicator bot logs will be written to {log_file}")

# Load env variables directly from .env file
load_dotenv()

# Try to get token from environment directly first, then fallback to settings
COMMUNICATOR_BOT_TOKEN = os.environ.get("COMMUNICATOR_BOT_TOKEN")
if not COMMUNICATOR_BOT_TOKEN:
    # Fallback to settings
    settings = get_settings()
    COMMUNICATOR_BOT_TOKEN = settings.COMMUNICATOR_BOT_TOKEN
    logger.info("Token loaded from settings")
else:
    logger.info("Token loaded directly from environment")

# Log token first few characters for debugging
if COMMUNICATOR_BOT_TOKEN:
    logger.info("Token loaded successfully")
else:
    logger.error("No token found!")

# Global variables for clean shutdown
bot = None
dp = None
should_exit = False

# Setup health check server
async def setup_health_server():
    """Set up a health check web server for Railway."""
    port = os.environ.get("PORT", "8080")
    
    # Create a simple health check endpoint
    async def health_handler(request):
        """Handler for /health endpoint."""
        logger.debug("Health check received")
        return web.Response(text="Communicator bot is running")
    
    app = web.Application()
    app.router.add_get("/health", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(port))
    await site.start()
    
    logger.info(f"Health check server running on port {port}")
    
    # Keep the server running
    while not should_exit:
        await asyncio.sleep(1)
    
    # Cleanup when exiting
    logger.info("Shutting down health check server")
    await runner.cleanup()

async def reset_webhook():
    """Reset the Telegram webhook to ensure no conflicts."""
    if not COMMUNICATOR_BOT_TOKEN:
        logger.error("Cannot reset webhook: No token available")
        return False
        
    try:
        logger.info("Resetting Telegram webhook...")
        # Create a default SSL context that doesn't verify
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Create a session with relaxed SSL configuration
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            # First, check current webhook status
            async with session.get(
                f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/getWebhookInfo"
            ) as response:
                webhook_info = await response.json()
                logger.info(f"Current webhook status: {webhook_info}")
            
            # Force delete the webhook with drop_pending_updates
            async with session.get(
                f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
            ) as response:
                result = await response.json()
                if result.get("ok"):
                    logger.info("Webhook deleted successfully")
                else:
                    logger.error(f"Failed to delete webhook: {result}")
                    return False
                    
            # Verify webhook was deleted
            await asyncio.sleep(1)  # Give Telegram a moment to process
            async with session.get(
                f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/getWebhookInfo"
            ) as response:
                webhook_info = await response.json()
                if webhook_info.get("ok") and not webhook_info.get("result", {}).get("url"):
                    logger.info("Verified webhook is now empty")
                    return True
                else:
                    logger.warning(f"Webhook might still be active: {webhook_info}")
                    return False
    except Exception as e:
        logger.error(f"Error resetting webhook: {e}")
        return False

async def shutdown(signal_name=None):
    """Shutdown the bot gracefully."""
    global bot, should_exit
    
    if signal_name:
        logger.info(f"Received {signal_name}, shutting down...")
    
    # Set the exit flag for health server
    should_exit = True
    
    # Close bot session properly
    if bot:
        logger.info("Closing bot connection...")
        await bot.session.close()
    
    logger.info("Communicator bot stopped.")

async def start_communicator_bot() -> None:
    """Initialize and start the communicator bot."""
    global bot, dp, should_exit
    
    if not COMMUNICATOR_BOT_TOKEN:
        logger.error("Communicator Bot Token not found!")
        return

    # Start health check server in a separate task
    health_server_task = asyncio.create_task(setup_health_server())
    logger.info("Health check server task created")

    # Reset webhook before starting
    if not await reset_webhook():
        logger.warning("Could not reset webhook completely, will try one more time...")
        # Wait a bit and try one more time
        await asyncio.sleep(5)
        if not await reset_webhook():
            logger.error("Failed to reset webhook after multiple attempts, this may cause conflicts!")

    # Kill any other running instances by name
    try:
        import subprocess
        # This will only work on Unix systems, but it's a helpful safety check
        logger.info("Checking for other communicator bot processes...")
        result = subprocess.run(
            "ps aux | grep 'src.communicator_bot.main' | grep -v grep | awk '{print $2}'", 
            shell=True, 
            capture_output=True, 
            text=True
        )
        pids = result.stdout.strip().split('\n')
        current_pid = os.getpid()
        
        for pid in pids:
            if pid and pid.isdigit() and int(pid) != current_pid:
                logger.warning(f"Found another communicator bot process with PID {pid}, attempting to terminate it")
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to process {pid}")
                except Exception as e:
                    logger.error(f"Failed to terminate process {pid}: {e}")
    except Exception as e:
        logger.error(f"Error checking for other processes: {e}")

    try:
        logger.info("Creating bot instance with token...")
        bot = Bot(
            token=COMMUNICATOR_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

        # Verify token by getting bot info
        try:
            bot_info = await bot.get_me()
            logger.info(f"Bot verification successful: @{bot_info.username}")
        except Exception as e:
            logger.error(f"Bot verification failed: {e}")
            return

        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Register middlewares
        dp.update.middleware(BotMiddleware(bot))
        dp.update.middleware(DatabaseMiddleware())
        dp.update.middleware(LoggingMiddleware())

        register_handlers(dp)

        logger.info("Starting communicator bot...")
        
        # Give Telegram servers a moment to fully clear any previous connections
        logger.info("Waiting 5 seconds before starting polling to ensure clean state...")
        await asyncio.sleep(5)
        
        # Start polling with proper error handling and exponential backoff
        retry_count = 0
        max_retries = 10
        base_delay = 2
        
        while not should_exit and retry_count < max_retries:
            try:
                logger.info(f"Starting polling (attempt {retry_count+1}/{max_retries})...")
                await dp.start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member"])
                # If we get here, polling ended normally (unlikely)
                logger.info("Polling ended normally")
                break
            except Exception as e:
                if "Conflict:" in str(e):
                    retry_count += 1
                    delay = min(300, base_delay * (2 ** retry_count))  # Exponential backoff with 5 min max
                    logger.warning(f"Telegram conflict error: {e}")
                    logger.info(f"Waiting {delay} seconds before attempt {retry_count+1}/{max_retries}...")
                    
                    # Try to reset webhook again
                    await reset_webhook()
                    await asyncio.sleep(delay)
                else:
                    logger.exception(f"Error in bot polling: {e}")
                    if not should_exit:
                        retry_count += 1
                        delay = min(60, base_delay * (2 ** retry_count))  # Exponential backoff with 1 min max
                        logger.info(f"Waiting {delay} seconds before attempt {retry_count+1}/{max_retries}...")
                        await asyncio.sleep(delay)
            
        if retry_count >= max_retries:
            logger.error(f"Failed to start polling after {max_retries} attempts, giving up")
    except Exception as e:
        logger.exception(f"Error starting communicator bot: {e}")
    finally:
        await shutdown()
        # Cancel the health server task
        if health_server_task and not health_server_task.done():
            health_server_task.cancel()
            try:
                await health_server_task
            except asyncio.CancelledError:
                logger.info("Health server task cancelled")

def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    for sig_name in ('SIGINT', 'SIGTERM'):
        asyncio.get_event_loop().add_signal_handler(
            getattr(signal, sig_name),
            lambda sig_name=sig_name: asyncio.create_task(shutdown(sig_name))
        )

if __name__ == '__main__':
    # Setup signal handlers
    setup_signal_handlers()
    
    try:
        asyncio.run(start_communicator_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}") 