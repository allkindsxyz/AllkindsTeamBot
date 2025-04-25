# Simplified main.py for Allkinds Team Bot
# This version focuses on staying alive and responding to commands

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import asyncio
import time
import os
import json
import sys
import logging
import traceback
import psycopg2
from datetime import datetime
from typing import Dict, List, Any, Callable, Awaitable

from src.core.config import get_settings
from src.bot.handlers import register_handlers
from src.bot.middlewares import DbSessionMiddleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware
from src.db.base import async_session_factory
from src.core.diagnostics import configure_diagnostics, track_webhook, get_diagnostics_report, log_environment_vars

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Detect environment
IS_PRODUCTION = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
PORT = int(os.environ.get("PORT", 8000))

class MessageLoggingMiddleware:
    """Middleware for detailed logging of message processing"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        logger.info(f"Received message: {getattr(event, 'text', 'Non-text')} from user ID: {event.from_user.id}")
        try:
            result = await handler(event, data)
            return result
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            logger.error(traceback.format_exc())
            raise

async def health_check(request):
    """Health check endpoint that always returns OK."""
    logger.info(f"Health check requested from {request.remote}")
    return web.Response(text=json.dumps({"status": "ok", "time": time.time()}), 
                        content_type="application/json", status=200)

async def status_page(request):
    """Status page showing bot is running."""
    return web.Response(
        text=f"<html><body><h1>Bot is running</h1><p>Time: {datetime.now().isoformat()}</p></body></html>",
        content_type="text/html",
        status=200
    )

async def setup_webhook(bot, app, webhook_path):
    """Set up webhook for production environment."""
    webhook_domain = os.environ.get("WEBHOOK_DOMAIN")
    if not webhook_domain:
        logger.error("WEBHOOK_DOMAIN environment variable is not set")
        return False
    
    webhook_url = f"https://{webhook_domain}{webhook_path}"
    
    try:
        await bot.delete_webhook()
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
        logger.info(f"Webhook set to: {webhook_url}")
        
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url != webhook_url:
            logger.warning(f"Webhook URL mismatch. Got: {webhook_info.url}, Expected: {webhook_url}")
            return False
        
        logger.info(f"Webhook verified: {webhook_info.url}")
        return True
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        logger.exception("Webhook setup error details:")
        return False

async def main():
    """Main function to run the bot."""
    try:
        logger.info("Starting bot application...")
        
        # Log environment variables
        log_environment_vars()
        
        # Create bot instance
        bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
        logger.info("Bot created")
        
        # Create dispatcher
        dp = Dispatcher(storage=MemoryStorage())
        logger.info("Dispatcher created")
        
        # Register handlers
        try:
            register_handlers(dp)
            logger.info("Handlers registered")
        except Exception as e:
            logger.error(f"Error registering handlers: {e}")
        
        # Register middleware
        try:
            dp.message.middleware(MessageLoggingMiddleware())
            dp.update.outer_middleware(StateLoggingMiddleware())
            dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
            logger.info("Middleware registered")
        except Exception as e:
            logger.error(f"Error registering middleware: {e}")
        
        # Set commands
        try:
            await bot.set_my_commands([
                BotCommand(command="/start", description="Start the bot"),
                BotCommand(command="/help", description="Show help"),
                BotCommand(command="/cancel", description="Cancel operation")
            ])
            logger.info("Commands set")
        except Exception as e:
            logger.error(f"Error setting commands: {e}")
        
        # Create web application
        app = web.Application()
        
        # Set up SimpleRequestHandler
        webhook_path = f"/webhook/{settings.BOT_TOKEN}"
        
        # Create request handler
        webhook_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot
        )
        
        # Add bot to app context
        app["bot"] = bot
        
        # Register routes
        app.router.add_post(webhook_path, webhook_handler.handle)
        app.router.add_get("/health", health_check)
        app.router.add_get("/", status_page)
        
        # Set up webhook in production
        if IS_PRODUCTION:
            webhook_success = await setup_webhook(bot, app, webhook_path)
            if not webhook_success:
                logger.warning("Webhook setup was not successful")
        else:
            # Delete webhook for development
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted for development mode")
        
        # Start web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        
        await site.start()
        logger.info(f"Web server started on port {PORT}")
        
        # Create a keep-alive task
        async def keep_alive():
            while True:
                try:
                    logger.info(f"Keep-alive check at {datetime.now().isoformat()}")
                    me = await bot.get_me()
                    logger.info(f"Bot connected as @{me.username}")
                    
                    # Check webhook status if in production
                    if IS_PRODUCTION:
                        webhook_info = await bot.get_webhook_info()
                        logger.info(f"Webhook URL: {webhook_info.url}")
                        
                        # Fix webhook if needed
                        if webhook_info.last_error_message:
                            logger.error(f"Webhook error: {webhook_info.last_error_message}")
                            await setup_webhook(bot, app, webhook_path)
                except Exception as e:
                    logger.error(f"Error in keep-alive check: {e}")
                
                # Wait 5 minutes before next check
                await asyncio.sleep(300)
        
        # Start keep-alive task
        asyncio.create_task(keep_alive())
        
        # Keep the application running indefinitely
        logger.info("Bot is now running")
        
        # Wait forever - essential for Railway
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"Unhandled error in main function: {e}")
        logger.exception("Main function error details:")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually")
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        logger.exception("Critical error details:")
