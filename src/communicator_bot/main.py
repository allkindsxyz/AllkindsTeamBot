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
from aiogram import types
import json

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
    
    # Try with direct HTTP request as fallback
    try:
        import requests
        logger.info("Trying reset webhook with direct HTTP request as fallback...")
        response = requests.get(
            f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        )
        result = response.json()
        if result.get("ok"):
            logger.info("Webhook deleted successfully with direct HTTP request")
            return True
        else:
            logger.error(f"Failed to delete webhook with direct request: {result}")
    except Exception as e:
        logger.error(f"Error with direct webhook reset: {e}")
        
    # Try with aiohttp client
    try:
        logger.info("Resetting Telegram webhook using aiohttp...")
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
                    return True
                else:
                    logger.error(f"Failed to delete webhook: {result}")
                    
            # Verify webhook was deleted
            await asyncio.sleep(1)  # Give Telegram a moment to process
            async with session.get(
                f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/getWebhookInfo"
            ) as response:
                webhook_info = await response.json()
                if webhook_info.get("ok") and not webhook_info.get("result", {}).get("url"):
                    logger.info("Verified webhook is now empty")
                    return True
    except Exception as e:
        logger.error(f"Error resetting webhook: {e}")
    
    return False

async def setup_webhook_server():
    """Set up a web server for webhooks and health checks."""
    try:
        port = int(os.environ.get("COMMUNICATOR_PORT", 8082))
        logger.info(f"Setting up communicator webhook server on port {port}")
        
        app = web.Application()
        
        async def ping_handler(request):
            """Simple ping handler for health checks."""
            return web.Response(text='{"status":"ok","service":"communicator_bot"}', 
                               content_type='application/json')
                               
        async def health_handler(request):
            """Health check handler for Railway."""
            return web.Response(text='{"status":"ok","service":"communicator_bot"}', 
                               content_type='application/json')
                               
        async def webhook_handler(request):
            """Handle webhook updates from Telegram."""
            if request.content_type != 'application/json':
                return web.Response(status=415, text='Only JSON is accepted')
                
            try:
                data = await request.read()
                logger.info(f"Received webhook update: {len(data)} bytes")
                
                # Log message text if available for debugging
                try:
                    update_json = json.loads(data)
                    if "message" in update_json and "text" in update_json["message"]:
                        text = update_json["message"]["text"]
                        logger.info(f"Message text: {text}")
                except Exception:
                    pass
                
                # Process update with the bot
                update = types.Update.model_validate_json(data)
                await dp.feed_update(bot=bot, update=update)
                
                return web.Response(text='{"ok":true}', content_type='application/json')
            except Exception as e:
                logger.error(f"Error processing webhook update: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return web.Response(text='{"ok":false,"error":"Internal Server Error"}', 
                                   content_type='application/json', status=500)
        
        async def root_handler(request):
            """Root path handler for diagnostics."""
            return web.Response(text="Allkinds Communicator Bot is running. Use the Telegram app to interact with the bot.")
        
        # Add routes
        app.router.add_get("/ping", ping_handler)
        app.router.add_get("/health", health_handler)
        app.router.add_get("/", root_handler)
        app.router.add_post("/webhook", webhook_handler)
        
        # Start the server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        
        logger.info(f"Webhook server running on http://0.0.0.0:{port}")
        
        # Configure webhook URL
        webhook_host = os.environ.get("WEBHOOK_HOST")
        if webhook_host:
            webhook_url = f"{webhook_host}/webhook"
            logger.info(f"Setting webhook URL: {webhook_url}")
            
            try:
                await bot.set_webhook(webhook_url)
                logger.info("Webhook set successfully")
            except Exception as e:
                logger.error(f"Failed to set webhook: {e}")
        else:
            logger.warning("No webhook host set, skipping webhook configuration")
        
        # Keep running until signal to exit
        while not should_exit:
            await asyncio.sleep(1)
            
        # Cleanup
        logger.info("Shutting down webhook server")
        await runner.cleanup()
    except Exception as e:
        logger.error(f"Error setting up webhook server: {e}")

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

    # Reset webhook before starting
    if not await reset_webhook():
        logger.warning("Could not reset webhook completely, will try one more time...")
        # Wait a bit and try one more time
        await asyncio.sleep(5)
        if not await reset_webhook():
            logger.error("Failed to reset webhook after multiple attempts, this may cause conflicts!")

    try:
        logger.info("Creating bot instance with token...")
        bot = Bot(
            token=COMMUNICATOR_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

        # Verify token by getting bot info
        try:
            # Check for bot username in environment
            bot_username = os.environ.get("COMMUNICATOR_BOT_USERNAME", "")
            if not bot_username:
                from src.core.config import get_settings
                settings = get_settings()
                bot_username = settings.COMMUNICATOR_BOT_USERNAME
                logger.info(f"Using bot username from settings: {bot_username}")
            else:
                logger.info(f"Using bot username from environment: {bot_username}")

            # Remove @ if it's included
            if bot_username and bot_username.startswith("@"):
                bot_username = bot_username[1:]
                logger.info(f"Removed @ prefix from bot username")
                
            bot_info = await bot.get_me()
            logger.info(f"Bot verification successful: @{bot_info.username}")
        except Exception as e:
            logger.error(f"Bot verification failed: {e}")
            
            # Log detailed error for debugging
            import traceback
            logger.error(f"Bot verification traceback: {traceback.format_exc()}")
            return

        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Register middlewares
        dp.update.middleware(BotMiddleware(bot))
        dp.update.middleware(DatabaseMiddleware())
        dp.update.middleware(LoggingMiddleware())

        register_handlers(dp)

        logger.info("Starting communicator bot in webhook mode...")
        await setup_webhook_server()
        
    except Exception as e:
        logger.exception(f"Error starting communicator bot: {e}")
    finally:
        await shutdown()

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