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
import signal
import atexit
import socket
from datetime import datetime, UTC
from pathlib import Path
from contextlib import asynccontextmanager
import ssl
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from src.core.config import get_settings
from src.bot.handlers import register_handlers
from src.bot.middlewares import DbSessionMiddleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware
from src.db.base import async_session_factory
from src.db import get_async_engine, init_models, get_session
from src.core.diagnostics import get_diagnostics_report, IS_RAILWAY

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

# Lock file path
LOCK_FILE = "bot.lock"

def check_lock_file():
    """Check if the lock file exists and if the process is still running."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                data = json.load(f)
            
            # Check if the process ID exists
            pid = data.get("pid")
            if pid:
                try:
                    # Try to send signal 0 to the process (doesn't kill it, just checks if exists)
                    os.kill(pid, 0)
                    hostname = data.get("hostname", "unknown")
                    started_at = data.get("started_at", "unknown time")
                    
                    # Process exists, bot is already running
                    logger.error(f"Bot is already running with PID {pid} on {hostname} since {started_at}")
                    logger.error("To force start, delete the lock file: bot.lock")
                    return False
                except OSError:
                    # Process doesn't exist, we can remove the lock file
                    logger.warning(f"Found stale lock file for non-existent process {pid}. Removing it.")
                    os.remove(LOCK_FILE)
        except Exception as e:
            # Error reading or parsing the lock file
            logger.warning(f"Error checking lock file: {e}")
            logger.warning("Removing potentially corrupted lock file")
            try:
                os.remove(LOCK_FILE)
            except:
                pass
    
    # Create lock file
    try:
        with open(LOCK_FILE, "w") as f:
            data = {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "started_at": datetime.now(UTC).isoformat()
            }
            json.dump(data, f)
        logger.info(f"Created lock file for PID {os.getpid()}")
    except Exception as e:
        logger.error(f"Failed to create lock file: {e}")
    
    # Register cleanup on exit
    atexit.register(remove_lock_file)
    
    return True

def remove_lock_file():
    """Remove the lock file on exit."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("Removed lock file")
    except Exception as e:
        logger.error(f"Failed to remove lock file: {e}")

async def on_shutdown(dispatcher: Dispatcher, bot: Bot):
    """Handle shutdown processes."""
    logger.info("Shutting down the bot")
    await dispatcher.fsm.storage.close()
    await bot.session.close()
    logger.info("Bot shutdown complete")

async def run_webhook_bot():
    """Run the bot in webhook mode."""
    logger.info("Starting bot in webhook mode")
    
    webhook_host = settings.WEBHOOK_HOST
    webhook_path = settings.WEBHOOK_PATH
    webapp_host = settings.WEBAPP_HOST
    webapp_port = settings.WEBAPP_PORT
    
    # Set up SSL if using HTTPS
    ssl_context = None
    if settings.WEBHOOK_HOST.startswith("https"):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        ssl_context.load_cert_chain(settings.WEBHOOK_SSL_CERT, settings.WEBHOOK_SSL_PRIV)
    
    # Initialize the bot with an AiohttpSession for better control
    bot_session = AiohttpSession()
    bot = Bot(token=settings.BOT_TOKEN, session=bot_session, default=DefaultBotProperties(parse_mode="HTML"))
    
    # Configure storage - Redis if available, otherwise Memory
    if settings.REDIS_URL:
        storage = RedisStorage.from_url(settings.REDIS_URL)
        logger.info("Using Redis storage for FSM")
    else:
        storage = MemoryStorage()
        logger.info("Using in-memory storage for FSM")
    
    # Initialize dispatcher
    dp = Dispatcher(storage=storage)
    
    # Register all the middleware
    register_middlewares(dp)
    
    # Register all the handlers
    register_handlers(dp)
    
    # Set up webhook
    webhook_url = f"{webhook_host}{webhook_path}"
    await bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to {webhook_url}")
    
    # Start aiohttp application for webhook
    app = web.Application()
    
    # Simple handler for health checks
    async def health_handler(request):
        return web.Response(text="Bot is running")
    
    # Webhook handler
    async def webhook_handler(request):
        try:
            # Get the request data
            data = await request.json()
            # Create a telegram Update object
            update = types.Update.model_validate(data, context={"bot": bot})
            # Process the update using the dispatcher
            await dp.feed_update(bot, update)
            return web.Response()
        except Exception as e:
            logger.error(f"Error in webhook handler: {e}")
            traceback.print_exc()
            return web.Response(status=500)
    
    # Add the routes
    app.router.add_get("/health", health_handler)
    app.router.add_post(webhook_path, webhook_handler)
    
    # Set up shutdown routine
    async def shutdown_app(app):
        await on_shutdown(dp, bot)
    
    app.on_shutdown.append(shutdown_app)
    
    # Start the web server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, webapp_host, webapp_port, ssl_context=ssl_context)
    
    logger.info(f"Starting webhook listener on {webapp_host}:{webapp_port}")
    await site.start()
    
    # Keep the process alive
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour, let things run
    except asyncio.CancelledError:
        logger.info("Bot received cancellation signal")
    finally:
        logger.info("Shutting down webhook listener")
        await runner.cleanup()

async def run_polling_bot():
    """Run the bot in polling mode."""
    logger.info("Starting bot in polling mode")
    
    # Initialize the bot with an AiohttpSession for better control
    bot_session = AiohttpSession()
    bot = Bot(token=settings.BOT_TOKEN, session=bot_session, default=DefaultBotProperties(parse_mode="HTML"))
    
    # Configure storage
    if settings.REDIS_URL:
        storage = RedisStorage.from_url(settings.REDIS_URL)
        logger.info("Using Redis storage for FSM")
    else:
        storage = MemoryStorage()
        logger.info("Using in-memory storage for FSM")
    
    # Initialize dispatcher
    dp = Dispatcher(storage=storage)
    
    # Register all the middleware
    register_middlewares(dp)
    
    # Register all the handlers
    register_handlers(dp)
    
    # Make sure webhook is removed
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook removed, using polling mode")
    
    # Log diagnostic info
    diagnostics = get_diagnostics_report()
    logger.info(f"System diagnostics: {diagnostics}")
    
    # Set up signal handlers
    def signal_handler(*args):
        logger.info("Received termination signal")
        raise asyncio.CancelledError()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, signal_handler)
        except (AttributeError, RuntimeError):
            # Windows doesn't support SIGTERM
            pass
    
    # Start polling
    try:
        logger.info("Bot started polling for updates. Press Ctrl+C to stop")
        await dp.start_polling(bot, skip_updates=True)
    except asyncio.CancelledError:
        logger.info("Bot polling cancelled")
    finally:
        await on_shutdown(dp, bot)

@asynccontextmanager
async def lifespan(app: web.Application):
    """
    Lifespan context manager for the web application.
    Handles database startup and shutdown cleanly.
    """
    # Database setup
    engine = get_async_engine(settings.DATABASE_URL)
    await init_models(engine)
    
    # Start the bot here (use await asyncio.create_task if needed)
    # Yield to let the application run
    yield
    
    # Cleanup on shutdown
    logger.info("Application shutting down, cleaning up resources")

async def main():
    """Main entry point for the bot."""
    logger.info("==================================================")
    logger.info(f"Starting AllkindsTeamBot at {datetime.now(UTC).isoformat()}")
    logger.info(f"Running in {'Railway' if IS_RAILWAY else 'Local'} environment")
    
    # Check if another instance is running
    if not check_lock_file():
        logger.error("Bot is already running, exiting")
        return
    
    try:
        # Check for database migrations
        if not os.environ.get("SKIP_DB_INIT"):
            engine = get_async_engine(settings.DATABASE_URL)
            await init_models(engine)
            logger.info("Database initialized")
        
        # Decide between webhook and polling modes
        if settings.USE_WEBHOOK:
            await run_webhook_bot()
        else:
            await run_polling_bot()
    except Exception as e:
        logger.error(f"Critical error in main function: {e}")
        traceback.print_exc()
    finally:
        remove_lock_file()
        logger.info(f"Bot stopped at {datetime.now(UTC).isoformat()}")
        logger.info("==================================================")

if __name__ == "__main__":
    # Start the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
