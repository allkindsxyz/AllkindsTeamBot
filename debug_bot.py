#!/usr/bin/env python3
"""
Debug script for the Allkinds Telegram Bot.
This script will:
1. Verify the bot token works
2. Check bot permissions
3. Test webhook vs polling mode
4. Check handler registration
5. Test receiving a simple /start command
"""

import os
import sys
import asyncio
import signal
import logging
from datetime import datetime
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("debug_bot")

try:
    # Import bot dependencies
    from aiogram import Bot, Dispatcher, types
    from aiogram.filters import Command
    from aiogram.types import Message
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.fsm.storage.memory import MemoryStorage
    from loguru import logger as loguru_logger
except ImportError as e:
    logger.error(f"Failed to import aiogram: {e}")
    logger.error("Please make sure you've installed all dependencies: pip install -r requirements.txt")
    sys.exit(1)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("No BOT_TOKEN environment variable found!")
    sys.exit(1)

async def test_bot_token():
    """Test if the bot token is valid by getting bot info."""
    logger.info("Testing bot token...")
    
    try:
        # Create a bot instance with default session
        bot = Bot(token=BOT_TOKEN)
        
        # Try to get bot information
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot token is valid! Bot username: @{bot_info.username}")
        logger.info(f"Bot ID: {bot_info.id}")
        logger.info(f"Bot name: {bot_info.first_name}")
        
        # Close the session
        await bot.session.close()
        
        return True
    except Exception as e:
        logger.error(f"❌ Bot token test failed: {e}")
        traceback.print_exc()
        return False

async def test_webhook_setup():
    """Test the bot's webhook setup."""
    logger.info("Testing webhook configuration...")
    
    try:
        # Create a bot instance
        bot = Bot(token=BOT_TOKEN)
        
        # Check current webhook
        webhook_info = await bot.get_webhook_info()
        
        if webhook_info.url:
            logger.info(f"ℹ️ Bot has an active webhook set to: {webhook_info.url}")
            logger.info(f"Pending updates: {webhook_info.pending_update_count}")
            logger.info(f"Last error: {webhook_info.last_error_message or 'None'}")
            
            # Try deleting the webhook
            logger.info("Attempting to delete the webhook...")
            await bot.delete_webhook(drop_pending_updates=True)
            
            # Verify it was deleted
            webhook_info = await bot.get_webhook_info()
            if not webhook_info.url:
                logger.info("✅ Webhook successfully deleted")
            else:
                logger.warning(f"⚠️ Failed to delete webhook, still set to: {webhook_info.url}")
        else:
            logger.info("✅ No webhook is currently set (ready for polling mode)")
        
        # Close the session
        await bot.session.close()
        
        return True
    except Exception as e:
        logger.error(f"❌ Webhook test failed: {e}")
        traceback.print_exc()
        return False

async def test_receive_messages():
    """Test if the bot can receive and process messages."""
    logger.info("Testing message handling in polling mode...")
    
    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        logger.info("Received termination signal")
        shutdown_event.set()
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal_handler)
    
    try:
        # Create bot with AiohttpSession for better control
        bot_session = AiohttpSession()
        bot = Bot(token=BOT_TOKEN, session=bot_session, default=DefaultBotProperties(parse_mode="HTML"))
        
        # Configure storage
        storage = MemoryStorage()
        
        # Initialize dispatcher
        dp = Dispatcher(storage=storage)
        
        # Define a simple command handler
        @dp.message(Command("start"))
        async def cmd_start(message: Message):
            user = message.from_user
            logger.info(f"Received /start command from user @{user.username or user.id}")
            await message.answer(f"Hello, {user.first_name}! The bot is working correctly!")
            logger.info("✅ Successfully replied to /start command")
        
        # Define a handler for all messages
        @dp.message()
        async def echo_handler(message: Message):
            logger.info(f"Received message: {message.text}")
            await message.answer(f"Echo: {message.text}")
        
        # Make sure webhook is removed
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook removed, ready for polling")
        
        # Start polling in the background
        polling_task = asyncio.create_task(
            dp.start_polling(bot, skip_updates=True)
        )
        
        logger.info("Bot started in polling mode!")
        logger.info("Waiting for messages... Send /start to your bot.")
        logger.info("Press Ctrl+C to stop")
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Cancel polling task
        polling_task.cancel()
        
        # Wait for task to be cancelled
        try:
            await polling_task
        except asyncio.CancelledError:
            logger.info("Polling task cancelled")
        
        # Close sessions
        await dp.fsm.storage.close()
        await bot.session.close()
        
        return True
    except Exception as e:
        logger.error(f"❌ Message handling test failed: {e}")
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    logger.info("=== ALLKINDS TELEGRAM BOT DEBUGGER ===")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    
    # Test the bot token
    if not await test_bot_token():
        logger.error("❌ Bot token test failed. Please check your BOT_TOKEN environment variable.")
        return
    
    # Test webhook configuration
    if not await test_webhook_setup():
        logger.error("❌ Webhook configuration test failed.")
        return
    
    # Test message handling
    await test_receive_messages()
    
    logger.info("=== DEBUG COMPLETED ===")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Debug script stopped by user")
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        traceback.print_exc() 