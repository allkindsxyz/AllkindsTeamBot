from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramConflictError
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from loguru import logger
import asyncio
import time
import os
import json
import sys
import logging
import traceback
import psycopg2

# from src.bot.config import bot_settings # No longer needed
from src.core.config import get_settings # Import main settings
from src.bot.handlers import register_handlers
from src.bot.middlewares import DbSessionMiddleware # Import middleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware # Import the new middleware
from src.db.base import async_session_factory # Import session factory
from src.core.diagnostics import configure_diagnostics, track_webhook, get_diagnostics_report # Import diagnostics

settings = get_settings()

# Detect environment (Railway or local)
IS_PRODUCTION = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
WEBHOOK_HOST = os.environ.get("WEBHOOK_DOMAIN", "https://allkinds-team-bot-production.up.railway.app")
WEBHOOK_PATH = f"/webhook/{settings.BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Webhook settings
WEBAPP_HOST = "0.0.0.0"  # Binding to all interfaces
WEBAPP_PORT = int(os.environ.get("PORT", 8000))  # Using PORT env var from Railway


async def on_startup(bot: Bot) -> None:
    """Initialize bot and set webhook when app starts."""
    # Ensure we have the bot token
    if not settings.BOT_TOKEN:
        logging.critical("BOT_TOKEN is not configured in settings! Cannot set webhook.")
        return

    # Determine the webhook domain:
    # 1. Use WEBHOOK_DOMAIN env var if set (for custom domains)
    # 2. Use RAILWAY_PUBLIC_DOMAIN env var if available (standard Railway deployment)
    # 3. Fallback/Error if neither is set
    webhook_domain = os.environ.get("WEBHOOK_DOMAIN", "").strip()
    if not webhook_domain:
        logging.warning("WEBHOOK_DOMAIN is not set. Trying RAILWAY_PUBLIC_DOMAIN...")
        webhook_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if not webhook_domain:
            logging.error("Neither WEBHOOK_DOMAIN nor RAILWAY_PUBLIC_DOMAIN are set! Cannot determine webhook URL.")
            # Optionally, you could attempt a very generic fallback, but it's risky:
            # service_name = os.environ.get("RAILWAY_SERVICE_NAME", "unknown-service")
            # project_id = os.environ.get("RAILWAY_PROJECT_ID", "unknown-project")
            # webhook_domain = f"{service_name}-{project_id}.up.railway.app"
            # logging.warning(f"Using generated fallback domain: {webhook_domain}")
            # For now, let's just fail if no domain is found
            return # Cannot proceed without a valid domain
        else:
            logging.info(f"Using RAILWAY_PUBLIC_DOMAIN: {webhook_domain}")
    else:
        logging.info(f"Using explicitly set WEBHOOK_DOMAIN: {webhook_domain}")

    # Construct the final webhook URL
    # Ensure domain has https:// prefix
    if not webhook_domain.startswith("http"):
        webhook_domain = f"https://{webhook_domain}"
    webhook_url = f"{webhook_domain}/webhook/{settings.BOT_TOKEN}"
    logging.info(f"Final Webhook URL to be set: {webhook_url}")

    # Get current webhook info
    current_webhook = await bot.get_webhook_info()
    logging.info(f"Current webhook status: URL={current_webhook.url}, pending_update_count={current_webhook.pending_update_count}")

    # Set the webhook only if it's different or not set
    if current_webhook.url != webhook_url:
        logging.info(f"Webhook URL needs to be updated (Current: '{current_webhook.url}', Target: '{webhook_url}').")
        await bot.delete_webhook(drop_pending_updates=True) # Drop pending updates during change
        logging.info("Deleted existing webhook configuration.")
        
        logging.info(f"Setting webhook to: {webhook_url}")
        result = await bot.set_webhook(webhook_url)
        if not result:
            logging.error(f"Failed to set webhook to {webhook_url}")
            return # Stop if webhook setting fails
        else:
            logging.info("Successfully set new webhook.")
            # Short delay after setting webhook can sometimes help
            await asyncio.sleep(1)
    else:
        logging.info("Webhook URL is already correctly set. Skipping update.")

    # Get webhook info again to verify it was set correctly
    try:
        webhook_info = await bot.get_webhook_info()
        logging.info(f"Verified webhook status: URL={webhook_info.url}, pending_update_count={webhook_info.pending_update_count}")
        if webhook_info.url != webhook_url:
            # This is a critical error - log extensively
            logging.critical(f"Webhook verification FAILED! Expected '{webhook_url}', but got '{webhook_info.url}'")
            logging.critical(f"This means Telegram won't send updates to your bot!")
            logging.critical(f"Domain: {webhook_domain}, RAILWAY_PUBLIC_DOMAIN: {os.environ.get('RAILWAY_PUBLIC_DOMAIN')}")
            # But don't abort - Railway may need time to propagate DNS changes
            logging.warning("Continuing startup despite webhook mismatch - will retry setting webhook later")
            
            # Schedule a retry after 30 seconds (DNS propagation may take time)
            async def retry_set_webhook():
                await asyncio.sleep(30)
                logging.info("Retrying webhook setup after delay...")
                await bot.delete_webhook(drop_pending_updates=False)
                retry_result = await bot.set_webhook(webhook_url)
                retry_info = await bot.get_webhook_info()
                logging.info(f"Retry result: {retry_result}, URL now: {retry_info.url}")
            
            asyncio.create_task(retry_set_webhook())
    except Exception as e:
        logging.error(f"Error verifying webhook info: {str(e)}")
        traceback.print_exc()

    # Test the connection to Telegram API
    try:
        me = await bot.get_me()
        logging.info(f"Bot info: id={me.id}, username={me.username}, first_name={me.first_name}")
    except Exception as e:
        logging.error(f"Error getting bot info: {str(e)}")
        traceback.print_exc()


async def on_shutdown(bot: Bot) -> None:
    """Clean up resources when app shuts down."""
    logger.info("Shutting down bot")
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()


# Health check handler for Railway
async def health_check(request):
    """Health check endpoint for Railway."""
    logger.info(f"Health check requested from {request.remote}")
    
    # Create a health status dictionary
    health_status = {
        "status": "ok",
        "time": time.time(),
        "checks": {}
    }
    
    # Check database connection
    try:
        if 'DATABASE_URL' in os.environ:
            conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
            cur = conn.cursor()
            cur.execute('SELECT 1')
            result = cur.fetchone()
            conn.close()
            if result and result[0] == 1:
                logger.info("Health check: Database connection successful")
                health_status["checks"]["database"] = "ok"
            else:
                logger.warning("Health check: Database query returned unexpected result")
                health_status["checks"]["database"] = "warning"
        else:
            logger.warning("Health check: DATABASE_URL not in environment variables")
            health_status["checks"]["database"] = "warning"
    except Exception as e:
        logger.error(f"Health check: Database error: {str(e)}")
        health_status["checks"]["database"] = "error"
    
    # Check Telegram bot API connection
    try:
        if hasattr(request.app, 'bot'):
            bot = request.app['bot']
            me = await bot.get_me()
            health_status["checks"]["telegram"] = "ok"
            health_status["bot_info"] = {
                "id": me.id,
                "username": me.username,
                "first_name": me.first_name
            }
            logger.info(f"Health check: Telegram API connection successful, bot: @{me.username}")
        else:
            logger.warning("Health check: Bot not available in app context")
            health_status["checks"]["telegram"] = "warning"
    except Exception as e:
        logger.error(f"Health check: Telegram API error: {str(e)}")
        health_status["checks"]["telegram"] = "error"
    
    # Check webhook status
    try:
        if hasattr(request.app, 'bot'):
            bot = request.app['bot']
            webhook_info = await bot.get_webhook_info()
            health_status["webhook"] = {
                "url": webhook_info.url,
                "pending_updates": webhook_info.pending_update_count,
                "max_connections": webhook_info.max_connections
            }
            logger.info(f"Health check: Webhook status checked, URL: {webhook_info.url}")
        else:
            logger.warning("Health check: Bot not available for webhook check")
            health_status["checks"]["webhook"] = "warning"
    except Exception as e:
        logger.error(f"Health check: Webhook check error: {str(e)}")
        health_status["checks"]["webhook"] = "error"
    
    # Always return 200 OK for Railway's health check system
    return web.Response(text="OK", content_type="text/plain", status=200)


# Diagnostics handler for Railway monitoring
async def diagnostics_handler(request):
    """Diagnostics endpoint for Railway."""
    logger.info(f"Diagnostics requested from {request.remote}")
    report = get_diagnostics_report()
    return web.Response(text=report, status=200)


# Debug handler for incoming webhook requests
@track_webhook
async def debug_webhook(request):
    # Detailed logging of the webhook request
    method = request.method
    headers = dict(request.headers)
    ip = request.client.host if hasattr(request, 'client') and hasattr(request.client, 'host') else "unknown"
    try:
        body = await request.json()
    except Exception as e:
        body = {"error": f"Failed to parse JSON body: {str(e)}"}
        try:
            body["raw"] = await request.text()
        except:
            body["raw"] = "Could not read raw body"
    
    logging.info(f"WEBHOOK REQUEST: method={method}, ip={ip}")
    logging.info(f"WEBHOOK HEADERS: {json.dumps(headers, indent=2)}")
    logging.info(f"WEBHOOK BODY: {json.dumps(body, indent=2)}")
    
    # Call the real handler (which is now the SimpleRequestHandler instance)
    # We need access to the handler instance here. Pass it via app context?
    # For simplicity, let's assume we get it from the request's app context
    # Note: This requires the handler to be stored in the app context during setup
    if 'webhook_handler' in request.app:
        real_handler = request.app['webhook_handler']
        try:
            # Log specific callback_query details if present
            if "callback_query" in body and "data" in body.get("callback_query", {}):
                callback_data = body["callback_query"]["data"]
                from_id = body["callback_query"].get("from", {}).get("id", "unknown")
                logging.info(f"Received callback: '{callback_data}' from user {from_id}")
            
            return await real_handler.handle(request) # SimpleRequestHandler uses handle()
        except Exception as handler_exc:
            logging.error(f"Error executing real webhook handler: {handler_exc}")
            logging.exception("Stack trace:")
            return web.Response(status=500, text="Internal Server Error in Handler")
    else:
        logging.error("Webhook handler instance not found in app context!")
        return web.Response(status=500, text="Internal Server Error: Handler not configured")


async def start_bot() -> None:
    """Initialize and start the bot.
    
    In production, this sets up webhooks.
    In development, it uses polling.
    """
    # Set up logging format
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Configure diagnostics if in Railway environment
    if IS_PRODUCTION:
        configure_diagnostics()
        logging.info("Railway diagnostics configured")
    
    # Parse admin IDs
    admin_ids = _get_admin_ids()
    logging.info(f"Starting bot with admin IDs: {admin_ids}")
    
    # Create bot and dispatcher (Aiogram v3 style)
    bot = Bot(token=settings.BOT_TOKEN)
    storage = MemoryStorage() # Initialize the storage
    dp = Dispatcher(storage=storage) # Pass storage to Dispatcher
    logger.info("Dispatcher initialized with MemoryStorage.") # Add log

    # Register state logging middleware FIRST (as outer middleware)
    dp.update.outer_middleware(StateLoggingMiddleware())
    logger.info("State logging middleware registered.")

    # Setup database middleware (after logging middleware)
    dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
    logger.info("Database session middleware registered.")

    # Register all handlers (after middlewares)
    register_handlers(dp)
    logging.info("All handlers registered. Logging button handlers:")
    for router in dp.sub_routers:
        for handler in router.message.handlers:
            if hasattr(handler.callback, "__name__"):
                callback_name = handler.callback.__name__
                # Log text button handlers specifically
                if hasattr(handler.filter, "text") and handler.filter.text:
                    logging.info(f"Text button handler: '{handler.filter.text}' -> {callback_name}")
    
    # Log callback query handlers specifically
    logging.info("Logging callback query handlers:")
    for router in dp.sub_routers:
        for handler in router.callback_query.handlers:
            if hasattr(handler.callback, "__name__"):
                callback_name = handler.callback.__name__
                # Log callback data filters 
                if hasattr(handler.filter, "data"):
                    logging.info(f"Callback handler: '{handler.filter.data}' -> {callback_name}")
                elif hasattr(handler, "filter") and hasattr(handler.filter, "startswith"):
                    logging.info(f"Callback startswith handler: '{handler.filter.startswith}' -> {callback_name}")
    
    # Get port from environment
    port_env = os.environ.get("PORT")
    logging.info(f"PORT environment variable: {port_env}")
    
    port = int(port_env) if port_env else 8080
    logging.info(f"Using port: {port}")
    
    # Use webhooks in production and polling in development
    force_polling = False

    if IS_PRODUCTION:  # Use webhooks in Railway production environment
        logging.info(f"Starting bot in PRODUCTION mode with webhooks")
        
        # Create the webhook request handler instance
        # Pass dispatcher and bot instance to the handler
        webhook_request_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            # Add any secret token validation here if needed
            # secret_token="YOUR_SECRET_TOKEN_IF_USED" 
        )
        
        # Create aiohttp application instance
        app = web.Application()
        
        # Store the handler and bot in the app context
        app['webhook_handler'] = webhook_request_handler
        app['bot'] = bot
        
        # Register webhook handler route using the debug wrapper
        # The debug_webhook function will internally call the real handler now
        webhook_path = f'/webhook/{settings.BOT_TOKEN}' 
        app.router.add_post(webhook_path, debug_webhook)
        
        # Add health check and diagnostics routes
        app.router.add_get('/health', health_check)
        app.router.add_get('/diagnostics', diagnostics_handler)
        
        # Add a status endpoint to show the bot is running
        async def status_handler(request):
            return web.Response(text=f"Bot is running. Webhook URL: {webhook_path}\nPython version: {sys.version}")
        app.router.add_get('/', status_handler)
        
        # Register startup and shutdown handlers directly with aiohttp
        # Pass the bot instance explicitly to avoid context issues
        async def app_startup(app_instance):
            try:
                logging.info("Running application startup...")
                await on_startup(bot) # Pass the bot instance directly
                logging.info("Application startup completed successfully")
            except Exception as e:
                logging.error(f"Error during startup: {e}")
                logging.exception("Startup exception details:")
                # Don't reraise - let the app continue running
            
        async def app_shutdown(app_instance):
            try:
                await on_shutdown(bot) # Pass the bot instance directly
            except Exception as e:
                logging.error(f"Error during shutdown: {e}")

        app.on_startup.append(app_startup)
        app.on_shutdown.append(app_shutdown)

        # Start the web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=WEBAPP_HOST, port=port)
        
        try:
            await site.start()
            logging.info(f"Webhook server started on {WEBAPP_HOST}:{port} at path {webhook_path}")
            
            # Test the webhook URL
            test_url = f"https://{os.environ.get('WEBHOOK_DOMAIN')}/webhook/{settings.BOT_TOKEN}"
            logging.info(f"Expected webhook URL: {test_url}")
            
            # Keep the application running indefinitely with a more robust approach
            # We'll log periodically to show we're still alive
            while True:
                logging.info("Bot is still running...")
                
                # Check if webhook is still set correctly
                try:
                    webhook_info = await bot.get_webhook_info()
                    logging.info(f"Current webhook: {webhook_info.url}")
                    logging.info(f"Pending updates: {webhook_info.pending_update_count}")
                    
                    # Test connection to Telegram
                    me = await bot.get_me()
                    logging.info(f"Bot info: id={me.id}, username={me.username}")
                except Exception as e:
                    logging.error(f"Error in webhook check: {e}")
                
                await asyncio.sleep(300)  # Log every 5 minutes
        except Exception as e:
            logging.critical(f"Failed to start web server: {e}")
            logging.exception("Web server startup error details:")
            raise  # Re-raise to end the program with error
        finally:
            logging.info("Web server loop exited")

    else: # This block will now run
        # In development or forced polling mode, use polling
        logging.info("Starting bot in POLLING mode (forced for debugging)") # Modify log
        # Ensure database middleware is registered if it wasn't above (it is)
        # dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
        # logger.info("Database session middleware registered for polling.")

        # Make sure to delete any existing webhook first before polling
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Deleted webhook before starting polling.")
        except Exception as e:
            logger.error(f"Could not delete webhook: {e}")

        # Pass bot instance here for polling (Aiogram v3 style)
        logger.info("Starting polling...")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"]) # Make sure start_polling is called


# Add function for parsing admin IDs
def _get_admin_ids():
    """Parse admin IDs from environment variable."""
    admin_ids_str = os.environ.get("ADMIN_IDS", "")
    if not admin_ids_str:
        return []
    
    try:
        # Split by commas and convert to integers
        admin_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(',') if id_str.strip()]
        return admin_ids
    except ValueError:
        logging.error(f"Invalid ADMIN_IDS format: {admin_ids_str}")
        return []

if __name__ == "__main__":
    # Configure logging (optional, adjust as needed)
    # logger.add("main_bot.log", rotation="1 week", level="INFO") # Optional file logging
    logger.info("Initializing main bot...")
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.exception("Main bot exited due to an error:")
