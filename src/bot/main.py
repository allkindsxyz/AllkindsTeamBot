"""
Minimal implementation of Telegram bot with only essential functionality.
Just enough to respond to /start and stay alive with health check endpoint.
"""

import os
import sys
import json
import logging
import asyncio
import time
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get bot token from environment
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("No BOT_TOKEN provided in environment variables!")
    sys.exit(1)

# Create bot instance
bot = Bot(token=BOT_TOKEN)

# Create dispatcher
dp = Dispatcher(storage=MemoryStorage())

# Simple /start command handler
@dp.message(lambda message: message.text == "/start")
async def start_command(message: Message):
    try:
        logger.info(f"Received /start command from user {message.from_user.id}")
        await message.answer("Hello! I'm the Allkinds Team Bot. Use /help to see available commands.")
    except Exception as e:
        logger.error(f"Error handling /start command: {e}")

# Simple /help command handler
@dp.message(lambda message: message.text == "/help")
async def help_command(message: Message):
    try:
        logger.info(f"Received /help command from user {message.from_user.id}")
        await message.answer("Available commands:\n/start - Start the bot\n/help - Show this help message")
    except Exception as e:
        logger.error(f"Error handling /help command: {e}")

# Health check endpoint
async def health_check(request):
    """Simple health check that always returns OK"""
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
    """Run the bot with minimal functionality"""
    try:
        logger.info("Starting minimal bot...")
        
        # Log environment for debugging
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Bot token: {BOT_TOKEN[:4]}...{BOT_TOKEN[-4:]}")
        logger.info(f"PORT: {os.environ.get('PORT', '8080')}")
        
        # Set up commands
        try:
            await bot.set_my_commands([
                BotCommand(command="/start", description="Start the bot"),
                BotCommand(command="/help", description="Show help")
            ])
            logger.info("Bot commands set")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")
        
        # Create web application
        app = web.Application()
        
        # Register routes
        webhook_path = f"/webhook/{BOT_TOKEN}"
        
        # Use SimpleRequestHandler-style approach
        async def handle_webhook(request):
            try:
                logger.info("Received webhook request")
                update_data = await request.json()
                await dp.feed_update(bot=bot, update=update_data)
                return web.Response(status=200)
            except Exception as e:
                logger.error(f"Error handling webhook: {e}")
                return web.Response(status=200)  # Still return 200 to prevent Telegram from retrying
        
        # Register routes
        app.router.add_post(webhook_path, handle_webhook)
        app.router.add_get("/health", health_check)
        app.router.add_get("/", status_page)
        
        # Set up webhook in production
        is_production = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
        if is_production:
            webhook_domain = os.environ.get("WEBHOOK_DOMAIN")
            if webhook_domain:
                webhook_url = f"https://{webhook_domain}{webhook_path}"
                try:
                    await bot.delete_webhook()
                    await bot.set_webhook(webhook_url, drop_pending_updates=True)
                    logger.info(f"Webhook set to: {webhook_url}")
                    
                    # Verify webhook
                    webhook_info = await bot.get_webhook_info()
                    logger.info(f"Webhook URL: {webhook_info.url}")
                except Exception as e:
                    logger.error(f"Error setting webhook: {e}")
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
            except Exception as e:
                logger.error(f"Error checking bot status: {e}")
            
            # Wait for 5 minutes
            await asyncio.sleep(300)
        
    except Exception as e:
        logger.error(f"Unhandled error in main function: {e}")
        logger.exception("Main function error details:")

if __name__ == "__main__":
    # Handle any critical exceptions
    try:
        # Run the async application
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually")
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        logger.exception("Critical error details:")
