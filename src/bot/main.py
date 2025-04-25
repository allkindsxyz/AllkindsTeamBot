from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramConflictError
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import Message, BotCommand
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
from datetime import datetime
from typing import Dict, List, Any, Callable, Awaitable

# from src.bot.config import bot_settings # No longer needed
from src.core.config import get_settings # Import main settings
from src.bot.handlers import register_handlers
from src.bot.middlewares import DbSessionMiddleware # Import middleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware # Import the new middleware
from src.db.base import async_session_factory # Import session factory
from src.core.diagnostics import configure_diagnostics, track_webhook, get_diagnostics_report, log_environment_vars # Import diagnostics

settings = get_settings()

# Detect environment (Railway or local)
IS_PRODUCTION = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
WEBHOOK_HOST = os.environ.get("WEBHOOK_DOMAIN", "https://allkinds-team-bot-production.up.railway.app")
WEBHOOK_PATH = f"/webhook/{settings.BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Webhook settings
WEBAPP_HOST = "0.0.0.0"  # Binding to all interfaces
WEBAPP_PORT = int(os.environ.get("PORT", 8000))  # Using PORT env var from Railway

# Add message tracing middleware for debugging
class MessageLoggingMiddleware:
    """Middleware for detailed logging of message processing"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        """Log detailed information about incoming messages and their processing"""
        now = datetime.now().isoformat()
        
        # For text messages, log the content
        if hasattr(event, 'text'):
            logger.info(f"[{now}] Received message: {event.text} from user ID: {event.from_user.id}")
            if event.text.startswith('/'):
                logger.info(f"[{now}] Command detected: {event.text}")
        else:
            logger.info(f"[{now}] Received non-text message from user ID: {event.from_user.id}")
        
        try:
            # Log that we're about to process the message with relevant data
            handler_name = handler.__name__ if hasattr(handler, "__name__") else str(handler)
            logger.info(f"[{now}] Processing with handler: {handler_name}")
            
            # Process the message and track time
            start_time = time.time()
            result = await handler(event, data)
            process_time = time.time() - start_time
            
            # Log success
            logger.info(f"[{now}] Handler completed in {process_time:.2f}s")
            return result
            
        except Exception as e:
            # Log the complete error information for debugging
            logger.error(f"[{now}] Error processing message: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            # Re-raise the exception for the error handler middleware to process
            raise

async def on_startup(bot: Bot) -> None:
    """Initialize bot and set webhook (if in production)."""
    
    # Only set webhook in production (Railway)
    if IS_PRODUCTION:
        logger.info("Setting up webhook in production environment")
        
        # Get webhook domain from environment
        webhook_domain = os.environ.get("WEBHOOK_DOMAIN")
        if not webhook_domain:
            logger.error("WEBHOOK_DOMAIN environment variable is not set")
            return
        
        # Format the full webhook URL with domain and token
        webhook_path = f'/webhook/{settings.BOT_TOKEN}'
        webhook_url = f"https://{webhook_domain}{webhook_path}"
        
        # Configure webhook settings 
        try:
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
                max_connections=100
            )
            logger.info(f"Webhook set to: {webhook_url}")
            
            # Verify webhook was set correctly
            webhook_info = await bot.get_webhook_info()
            logger.info(f"Webhook Info - URL: {webhook_info.url}")
            logger.info(f"Webhook Info - Pending Updates: {webhook_info.pending_update_count}")
            logger.info(f"Webhook Info - Max Connections: {webhook_info.max_connections}")
            
            # Verify the webhook URL matches what we expect
            if webhook_info.url != webhook_url:
                logger.warning(f"Webhook URL mismatch. Expected: {webhook_url}, Got: {webhook_info.url}")
                
                # If there's a severe mismatch, try setting it again
                if not webhook_info.url or webhook_domain not in webhook_info.url:
                    logger.warning("Severe webhook URL mismatch. Attempting to set again...")
                    
                    # Define retry function with exponential backoff
                    async def retry_set_webhook():
                        max_retries = 5
                        for i in range(max_retries):
                            try:
                                # Delete any existing webhook first
                                await bot.delete_webhook()
                                logger.info("Deleted existing webhook before retry")
                                
                                # Wait with exponential backoff
                                wait_time = 2 ** i
                                await asyncio.sleep(wait_time)
                                
                                # Try setting the webhook again
                                await bot.set_webhook(
                                    url=webhook_url,
                                    drop_pending_updates=True,
                                    allowed_updates=["message", "callback_query"],
                                    max_connections=100
                                )
                                
                                # Verify it worked
                                new_info = await bot.get_webhook_info()
                                logger.info(f"Retry {i+1}: New webhook URL: {new_info.url}")
                                
                                if new_info.url == webhook_url:
                                    logger.info("Webhook set successfully after retry")
                                    return True
                                
                                logger.warning(f"Retry {i+1}: Webhook URL still doesn't match")
                            except Exception as e:
                                logger.error(f"Retry {i+1}: Error setting webhook: {e}")
                        
                        logger.error(f"Failed to set webhook after {max_retries} retries")
                        return False
                    
                    # Call the retry function
                    await retry_set_webhook()
            else:
                logger.info("Webhook URL verification successful")
                
            # Get bot user info to confirm API connection
            me = await bot.get_me()
            logger.info(f"Bot initialized as @{me.username} (ID: {me.id})")
            
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            logger.exception("Webhook setup error details:")
    else:
        # In development, make sure webhook is deleted
        logger.info("Development mode: Deleting webhook for polling")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted successfully")


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
        "timestamp": datetime.now().isoformat(),
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
                "max_connections": webhook_info.max_connections,
                "last_error_date": webhook_info.last_error_date,
                "last_error_message": webhook_info.last_error_message
            }
            
            if webhook_info.last_error_message:
                logger.error(f"Health check: Webhook has error: {webhook_info.last_error_message}")
                health_status["checks"]["webhook"] = "error"
            else:
                logger.info(f"Health check: Webhook status checked, URL: {webhook_info.url}")
                health_status["checks"]["webhook"] = "ok"
        else:
            logger.warning("Health check: Bot not available for webhook check")
            health_status["checks"]["webhook"] = "warning"
    except Exception as e:
        logger.error(f"Health check: Webhook check error: {str(e)}")
        health_status["checks"]["webhook"] = "error"
    
    # Add bot startup metrics
    health_status["metrics"] = {
        "webhook_calls": metrics.get("webhook_calls", 0),
        "db_operations": metrics.get("db_operations", 0),
        "command_calls": metrics.get("command_calls", 0),
        "errors": metrics.get("errors", 0),
        "last_webhook_time": metrics.get("last_webhook_time", None)
    }
    
    # Create the response text
    response_text = json.dumps(health_status, indent=2)
    
    # Log the full health check response for debugging
    logger.info(f"Health check response: {response_text}")
    
    # Always return 200 OK for Railway's health check system
    return web.Response(text=response_text, content_type="application/json", status=200)


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
        level=logging.DEBUG,  # Change to DEBUG for more detailed logs
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

    # Register detailed message logging middleware FIRST
    dp.message.middleware(MessageLoggingMiddleware())
    logger.info("Message logging middleware registered for debugging.")

    # Register state logging middleware as outer middleware
    dp.update.outer_middleware(StateLoggingMiddleware())
    logger.info("State logging middleware registered.")

    # Setup database middleware (after logging middleware)
    dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
    logger.info("Database session middleware registered.")

    # Register all handlers (after middlewares)
    register_handlers(dp)
    
    # Log available commands for debugging
    commands = [
        BotCommand(command="/start", description="Start the bot"),
        BotCommand(command="/help", description="Show help"),
        BotCommand(command="/cancel", description="Cancel current operation")
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info(f"Bot commands set: {[cmd.command for cmd in commands]}")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")

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
            # Create a "stay alive" task that continuously pings the health endpoint
            async def stay_alive():
                """Keep the application alive by continuously checking its health"""
                while True:
                    try:
                        # Log status every 5 minutes
                        logging.info(f"Bot health check - {datetime.now().isoformat()}")
                        
                        # Check webhook info
                        webhook_info = await bot.get_webhook_info()
                        logging.info(f"Webhook URL: {webhook_info.url}")
                        logging.info(f"Pending updates: {webhook_info.pending_update_count}")
                        
                        if webhook_info.last_error_message:
                            logging.error(f"Webhook error: {webhook_info.last_error_message}")
                            # If there's a webhook error, try to reset it
                            if webhook_info.url != test_url:
                                logging.warning("Webhook URL mismatch, attempting to reset...")
                                await bot.delete_webhook()
                                await asyncio.sleep(1)
                                await bot.set_webhook(
                                    url=test_url,
                                    drop_pending_updates=True,
                                    allowed_updates=["message", "callback_query"],
                                    max_connections=100
                                )
                                logging.info("Webhook reset attempted")
                        
                        # Check bot connection
                        me = await bot.get_me()
                        logging.info(f"Bot @{me.username} is active and connected to Telegram")
                        
                        # Add some CPU work to keep the process alive
                        # This prevents the process from being completely idle
                        sum_result = 0
                        for i in range(1000):
                            sum_result += i
                        
                        # Sleep for 5 minutes
                        await asyncio.sleep(300)
                    except Exception as e:
                        logging.error(f"Stay alive task error: {e}")
                        logging.exception("Stay alive exception details:")
                        # Sleep for 1 minute before retrying if there was an error
                        await asyncio.sleep(60)
            
            # Create a background task to keep the application alive
            keep_alive_task = asyncio.create_task(stay_alive())
            
            # Wait indefinitely (this is crucial for Railway to see the process as active)
            await asyncio.Event().wait()
            
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
    # Log all environment variables for debugging
    log_environment_vars()
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.exception("Main bot exited due to an error:")
