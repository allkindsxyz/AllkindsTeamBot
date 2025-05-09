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
from datetime import datetime, timezone
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
from src.bot.utils.webhook import reset_webhook
from src.bot.middlewares.db_middleware import DbSessionMiddleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware
from src.db.base import async_session_factory
from src.db import get_async_engine, init_models, get_session
from src.core.diagnostics import get_diagnostics_report, IS_RAILWAY
from src.core.startup import run_startup_tasks

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

# Add the start_bot function that is imported by src/main.py
async def start_bot():
    """Entry point for starting the bot, called from src/main.py"""
    logger.info("Starting bot via start_bot function")
    await main()

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
                "started_at": datetime.now(timezone.utc).isoformat()
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

def register_middlewares(dp: Dispatcher):
    """Register middlewares for the dispatcher."""
    logger.info("Registering middlewares")
    
    # Create database session pool - FIX: We should pass the factory itself, not call it
    # session_pool = async_session_factory()
    
    # Register database middleware with the factory, not an instance
    logger.info(f"Registering DbSessionMiddleware with factory of type: {type(async_session_factory)}")
    dp.update.middleware(DbSessionMiddleware(async_session_factory))
    
    # Register logging middleware
    dp.update.middleware(StateLoggingMiddleware())
    
    logger.info("Middlewares registered")

async def on_shutdown(dispatcher: Dispatcher, bot: Bot):
    """Handle shutdown processes with enhanced error handling."""
    logger.info("Shutting down the bot")
    try:
        await dispatcher.fsm.storage.close()
        logger.info("FSM storage closed")
    except Exception as e:
        logger.error(f"Error closing FSM storage: {e}")
    
    try:
        await bot.session.close()
        logger.info("Bot session closed")
    except Exception as e:
        logger.error(f"Error closing bot session: {e}")
    
    logger.info("Bot shutdown complete")

async def run_webhook_bot():
    """Run the bot in webhook mode."""
    logger.info("Starting bot in webhook mode")
    
    # Get webhook settings from environment
    webhook_host = os.environ.get("WEBHOOK_HOST")
    webhook_path = "/webhook"
    webapp_host = "0.0.0.0"
    webapp_port = int(os.environ.get("BOT_PORT", 8081))
    
    # Log webhook configuration for debugging
    logger.info(f"Webhook configuration:")
    logger.info(f"  HOST: {webhook_host}")
    logger.info(f"  PATH: {webhook_path}")
    logger.info(f"  Server listening on: {webapp_host}:{webapp_port}")
    
    # Set up SSL if using HTTPS
    ssl_context = None
    if webhook_host and webhook_host.startswith("https"):
        if os.path.exists(settings.WEBHOOK_SSL_CERT) and os.path.exists(settings.WEBHOOK_SSL_PRIV):
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            ssl_context.load_cert_chain(settings.WEBHOOK_SSL_CERT, settings.WEBHOOK_SSL_PRIV)
            logger.info("SSL context configured for webhook")
        else:
            logger.warning("SSL certificates not found, running without SSL")
    
    # Initialize the bot with an AiohttpSession for better control
    bot_session = AiohttpSession()
    bot = Bot(token=settings.BOT_TOKEN, session=bot_session, default=DefaultBotProperties(parse_mode="HTML"))
    
    # Configure storage
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        storage = RedisStorage.from_url(redis_url)
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
    try:
        if webhook_host:
            webhook_url = f"https://{webhook_host}/webhook"
            logger.info(f"Attempting to set webhook to {webhook_url}")
            await bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to {webhook_url}")
        else:
            logger.warning("No webhook host provided, skipping webhook setup")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        # Continue anyway - the application might still serve webhook requests
    
    # Start aiohttp application for webhook
    app = web.Application()
    
    # Simple handler for health checks
    async def health_handler(request):
        return web.Response(text='{"status":"ok","service":"main_bot"}', content_type='application/json')
    
    # Ping handler for internal health checks
    async def ping_handler(request):
        return web.Response(text='{"status":"ok"}', content_type='application/json')
    
    # Webhook handler with enhanced error handling
    async def webhook_handler(request):
        try:
            # Get the request data
            data = await request.read()
            logger.info(f"Received webhook update: {len(data)} bytes")
            
            # Create a telegram Update object
            update = types.Update.model_validate_json(data)
            
            # Process the update using the dispatcher
            await dp.feed_update(bot, update)
            return web.Response(text='{"ok":true}', content_type='application/json')
        except Exception as e:
            logger.error(f"Error in webhook handler: {e}")
            traceback.print_exc()
            return web.Response(status=500, text='{"ok":false,"error":"Internal error"}', 
                              content_type='application/json')
    
    # Add the routes
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ping", ping_handler)
    app.router.add_post(webhook_path, webhook_handler)
    logger.info(f"Added webhook handler at path: {webhook_path}")
    
    # Also add a handler for the root path for diagnostics
    async def root_handler(request):
        return web.Response(text="Allkinds Main Bot is running. Use the Telegram app to interact with the bot.")
    
    app.router.add_get("/", root_handler)
    logger.info(f"Added root handler at path: /")
    
    # Set up shutdown routine with robust cleanup
    async def shutdown_app(app):
        logger.info("Application shutdown initiated")
        try:
            await on_shutdown(dp, bot)
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        logger.info("Application shutdown completed")
    
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
            # Periodic health check and resource monitoring
            logger.debug("Webhook service health check")
            await asyncio.sleep(3600)  # Sleep for an hour, let things run
    except asyncio.CancelledError:
        logger.info("Bot received cancellation signal")
    except Exception as e:
        logger.error(f"Unexpected error in webhook loop: {e}")
    finally:
        logger.info("Shutting down webhook listener")
        try:
            await runner.cleanup()
        except Exception as e:
            logger.error(f"Error during web runner cleanup: {e}")

async def run_polling_bot():
    """Run the bot in polling mode."""
    logger.info("Starting bot in polling mode")
    
    # Initialize the bot with an AiohttpSession for better control
    bot_session = AiohttpSession()
    bot = Bot(token=settings.BOT_TOKEN, session=bot_session, default=DefaultBotProperties(parse_mode="HTML"))
    
    # Configure storage
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        storage = RedisStorage.from_url(redis_url)
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
    try:
        logger.info("Attempting to delete webhook")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook removed, using polling mode")
    except Exception as e:
        logger.error(f"Failed to delete webhook: {e}")
        logger.warning("Failed to delete webhook, continuing anyway")
        await asyncio.sleep(3)  # Wait a bit
        logger.info("Waiting 3 seconds for webhook to clear...")
    
    # Log diagnostic info
    diagnostics = get_diagnostics_report()
    logger.info(f"System diagnostics: {diagnostics}")
    
    # Ensure webhook is completely removed with retries
    for attempt in range(3):
        logger.info(f"Webhook deletion attempt {attempt+1}/3")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted successfully")
            # Verify deletion
            webhook_info = await bot.get_webhook_info()
            if not webhook_info.url:
                logger.info("Confirmed webhook is not set")
                break
            else:
                logger.warning(f"Webhook still set to {webhook_info.url}, retrying...")
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
        await asyncio.sleep(1)

    # Set up signal handlers
    def signal_handler(*args):
        logger.info("Received termination signal")
        raise asyncio.CancelledError()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, signal_handler)
        except (AttributeError, RuntimeError) as e:
            # Windows doesn't support SIGTERM
            logger.warning(f"Failed to set signal handler for {sig}: {e}")
    
    # Ensure webhook is reset properly
    logger.info("Resetting webhook before starting")
    success = await reset_webhook(bot)
    if not success:
        logger.warning("Failed to reset webhook properly, continuing anyway")

    # Start polling with enhanced exception handling
    try:
        logger.info("Bot started polling for updates. Press Ctrl+C to stop")
        await dp.start_polling(bot, skip_updates=True)
    except asyncio.CancelledError:
        logger.info("Bot polling cancelled")
    except Exception as e:
        logger.error(f"Error during polling: {e}")
        logger.exception("Full traceback:")
    finally:
        logger.info("Cleaning up polling bot resources")
        try:
            await on_shutdown(dp, bot)
        except Exception as e:
            logger.error(f"Error during bot cleanup: {e}")
        logger.info("Polling bot cleanup completed")

@asynccontextmanager
async def lifespan(app: web.Application):
    """
    Lifespan context manager for the web application.
    Handles database startup and shutdown cleanly.
    """
    # Database setup
    try:
        logger.info("Setting up database connection in lifespan context")
        engine = get_async_engine(settings.DB_URL)
        await init_models(engine)
        logger.info("Database setup completed")
    except Exception as e:
        logger.error(f"Error during database setup: {e}")
        logger.exception("Database setup error details:")
    
    # Yield to let the application run
    yield
    
    # Cleanup on shutdown
    logger.info("Application shutting down, cleaning up resources")

def register_all_handlers(dp: Dispatcher):
    """Register all command handlers with the dispatcher."""
    from src.bot.handlers import register_handlers
    
    # Register all handlers using the main registration function
    register_handlers(dp)
    logger.info("All handlers registered successfully")

async def setup_ping_server():
    """Setup a simple ping server for health checks on the specified port."""
    try:
        # Get port from environment or use default
        port = int(os.environ.get("WEBAPP_PORT", 8081))
        logger.info(f"Setting up ping server on port {port}")
        
        # Create a simple app with a ping endpoint
        app = web.Application()
        
        async def ping_handler(request):
            """Simple ping handler for health checks."""
            return web.Response(text='{"status":"ok"}', content_type='application/json')
            
        async def webhook_handler(request):
            """Webhook handler that logs requests."""
            try:
                body = await request.read()
                logger.info(f"Received webhook request: {len(body)} bytes")
                # Process webhook with bot's dispatcher
                await process_webhook_update(body)
                return web.Response(text='{"ok":true}', content_type='application/json')
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")
                return web.Response(text='{"ok":false,"error":"Internal Server Error"}', 
                                   content_type='application/json', status=500)
        
        # Add routes
        app.router.add_get("/ping", ping_handler)
        app.router.add_post("/webhook", webhook_handler)
        
        # Start the server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        
        logger.info(f"Ping server running on http://0.0.0.0:{port}/ping")
        
        # Keep the server running
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour
    except Exception as e:
        logger.error(f"Error setting up ping server: {e}")
        
async def process_webhook_update(data):
    """Process a webhook update with the bot's dispatcher."""
    global dp, bot
    
    if not dp or not bot:
        logger.error("Dispatcher or bot not initialized. Cannot process webhook.")
        return
        
    try:
        update = types.Update.model_validate_json(data)
        await dp.feed_update(bot=bot, update=update)
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}")
        
async def main():
    """Main function to initialize and start the bot."""
    try:
        # Display diagnostic information at startup
        diagnostics = get_diagnostics_report()
        logger.info(f"=== SYSTEM INFO ===\n{diagnostics}")
        
        # Start ping server in a separate task
        ping_server_task = asyncio.create_task(setup_ping_server())
        logger.info("Ping server task created")
        
        # Check if another instance is running
        if not check_lock_file():
            logger.error("Bot is already running, exiting")
            return
        
        try:
            # Check for database migrations
            if not os.environ.get("SKIP_DB_INIT"):
                engine = get_async_engine(settings.DB_URL)
                await init_models(engine)
                logger.info("Database initialized")
                
                # Run startup tasks for database integrity
                logger.info("Running startup integrity checks...")
                await run_startup_tasks()
            
            # Force polling mode regardless of settings
            logger.info("USE_WEBHOOK setting overridden to False, using polling mode")

            # Add detailed diagnostics
            logger.info("Starting bot in polling mode with detailed diagnostics:")
            logger.info(f"- Bot Token available: {bool(BOT_TOKEN)}")
            logger.info(f"- Database URL configured: {bool(settings.DB_URL)}")
            logger.info(f"- Using storage: {'Redis' if os.environ.get('REDIS_URL') else 'Memory'}")
            await run_polling_bot()
        except Exception as e:
            logger.error(f"Critical error in main function: {e}")
            traceback.print_exc()
        finally:
            remove_lock_file()
            logger.info(f"Bot stopped at {datetime.now(timezone.utc).isoformat()}")
            logger.info("==================================================")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # Start the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
