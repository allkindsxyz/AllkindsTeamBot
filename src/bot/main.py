"""
Enhanced implementation of Telegram bot with full functionality.
"""

import os
import sys
import json
import logging
import asyncio
import time
import traceback
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from src.core.config import get_settings
from src.bot.handlers import register_handlers
from src.bot.middlewares import DbSessionMiddleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware
from src.db.base import async_session_factory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Get bot token from environment
BOT_TOKEN = os.environ.get("BOT_TOKEN", settings.BOT_TOKEN)
if not BOT_TOKEN:
    logger.error("No BOT_TOKEN provided in environment variables!")
    sys.exit(1)

# Detect environment
IS_PRODUCTION = os.environ.get("RAILWAY_ENVIRONMENT") == "production"

# Health check endpoint
async def health_check(request):
    """Health check endpoint that always returns OK"""
    logger.info(f"Health check requested from {request.remote}")
    return web.Response(
        text=json.dumps({"status": "ok", "timestamp": datetime.now().isoformat()}),
        content_type="application/json",
        status=200
    )

# Status page
async def status_page(request):
    """Status page showing the bot is running"""
    return web.Response(
        text=f"<html><body><h1>Bot is running</h1><p>Time: {datetime.now().isoformat()}</p></body></html>",
        content_type="text/html",
        status=200
    )

# Main function
async def main():
    """Run the bot with full functionality"""
    try:
        logger.info("Starting main bot...")
        
        # Log environment for debugging
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Bot token: {BOT_TOKEN[:4]}...{BOT_TOKEN[-4:]}")
        logger.info(f"PORT: {os.environ.get('PORT', '8080')}")
        
        # Create bot instance
        bot = Bot(token=BOT_TOKEN)
        
        # Create dispatcher
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        logger.info("Dispatcher initialized with MemoryStorage")
        
        # Register middleware
        dp.update.outer_middleware(StateLoggingMiddleware())
        logger.info("State logging middleware registered")
        
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
        logger.info("Database session middleware registered")
        
        # Register all original handlers
        register_handlers(dp)
        logger.info("All handlers registered")
        
        # Set up commands
        try:
            await bot.set_my_commands([
                BotCommand(command="/start", description="Start the bot"),
                BotCommand(command="/help", description="Show help"),
                BotCommand(command="/cancel", description="Cancel operation")
            ])
            logger.info("Bot commands set")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")
        
        # Create web application
        app = web.Application()
        
        # Register routes
        webhook_path = f"/webhook/{BOT_TOKEN}"
        
        # Improved webhook handler
        async def handle_webhook(request):
            try:
                logger.info("Received webhook request")
                
                # Parse the update from the request
                update_data = await request.json()
                logger.debug(f"Update data: {json.dumps(update_data)[:200]}...")
                
                # Convert dict to Update object
                update = types.Update(**update_data)
                
                # Process the update
                await dp.feed_update(bot, update)
                
                return web.Response(status=200)
            except Exception as e:
                logger.error(f"Error handling webhook: {e}")
                logger.error(traceback.format_exc())
                return web.Response(status=200)  # Still return 200 to prevent Telegram from retrying
        
        # Register routes
        app.router.add_post(webhook_path, handle_webhook)
        app.router.add_get("/health", health_check)
        app.router.add_get("/", status_page)
        
        # Set up webhook in production
        if IS_PRODUCTION:
            webhook_domain = os.environ.get("WEBHOOK_DOMAIN")
            if webhook_domain:
                webhook_url = f"https://{webhook_domain}{webhook_path}"
                try:
                    # Delete existing webhook first
                    await bot.delete_webhook(drop_pending_updates=True)
                    # Set up new webhook
                    await bot.set_webhook(webhook_url, drop_pending_updates=True)
                    logger.info(f"Webhook set to: {webhook_url}")
                    
                    # Verify webhook
                    webhook_info = await bot.get_webhook_info()
                    logger.info(f"Webhook URL: {webhook_info.url}")
                    
                    # Check if set correctly
                    if webhook_info.url != webhook_url:
                        logger.warning(f"Webhook URL mismatch! Expected: {webhook_url}, Got: {webhook_info.url}")
                except Exception as e:
                    logger.error(f"Error setting webhook: {e}")
                    logger.error(traceback.format_exc())
            else:
                logger.error("WEBHOOK_DOMAIN environment variable not set!")
        else:
            # Delete webhook for development
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted for development mode")
        
        # Start web server
        port = int(os.environ.get("PORT", 8080))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        
        await site.start()
        logger.info(f"Web server started on port {port}")
        
        # Keep the service running
        logger.info("Bot is running indefinitely...")
        
        # Keep alive - log periodic status
        while True:
            logger.info(f"Bot status check at {datetime.now().isoformat()}")
            try:
                me = await bot.get_me()
                logger.info(f"Bot is connected as @{me.username} (ID: {me.id})")
                
                # Check webhook status in production
                if IS_PRODUCTION:
                    webhook_info = await bot.get_webhook_info()
                    logger.info(f"Webhook status: URL={webhook_info.url}, pending_updates={webhook_info.pending_update_count}")
                    
                    # If webhook is not set correctly, try to set it again
                    if webhook_domain and (not webhook_info.url or webhook_info.url != f"https://{webhook_domain}{webhook_path}"):
                        logger.warning("Webhook not set correctly, resetting...")
                        webhook_url = f"https://{webhook_domain}{webhook_path}"
                        await bot.delete_webhook()
                        await bot.set_webhook(webhook_url)
                        logger.info(f"Webhook reset to: {webhook_url}")
            except Exception as e:
                logger.error(f"Error checking bot status: {e}")
                logger.error(traceback.format_exc())
            
            # Wait for 5 minutes
            await asyncio.sleep(300)
        
    except Exception as e:
        logger.error(f"Unhandled error in main function: {e}")
        logger.exception(traceback.format_exc())

if __name__ == "__main__":
    # Handle any critical exceptions
    try:
        # Run the async application
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually")
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        logger.exception(traceback.format_exc())
