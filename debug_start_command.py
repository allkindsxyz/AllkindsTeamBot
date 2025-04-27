#!/usr/bin/env python3
"""
Debug script specifically for testing the /start command in the bot.
This script initializes a simple, standalone version of the bot with only
the start command handler registered, making it easier to debug issues.
"""

import os
import sys
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Import core components
from src.core.config import get_settings
from src.db import init_models
from src.db.base import async_session_factory
from src.bot.middlewares.db_middleware import DbSessionMiddleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware

# Import the start handler to debug
from src.bot.handlers.start import cmd_start

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Get the bot token from environment or settings
BOT_TOKEN = os.environ.get("BOT_TOKEN", settings.BOT_TOKEN)
if not BOT_TOKEN:
    logger.error("No BOT_TOKEN provided. Set it in .env or as an environment variable.")
    sys.exit(1)

async def main():
    """Initialize and run the debug bot."""
    logger.info("Initializing debug bot with focus on /start handler")
    
    # Initialize the bot
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Register database middleware
    session_pool = async_session_factory()
    dp.update.middleware(DbSessionMiddleware(session_pool))
    
    # Register logging middleware for additional debug info
    dp.update.middleware(StateLoggingMiddleware())
    
    # Only register the start command handler
    dp.message.register(cmd_start, Command("start"))
    
    # Initialize database
    logger.info("Initializing database")
    engine = create_async_engine(settings.db_url)
    await init_models(engine)
    
    # Remove webhook and start polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting polling with debug mode active")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"Error during polling: {e}", exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    try:
        logger.info("Starting debug script for /start command")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True) 