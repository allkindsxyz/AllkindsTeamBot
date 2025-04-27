#!/usr/bin/env python3
"""
Script to test the Group Info button functionality specifically.
"""

import os
import sys
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from src.bot.middlewares.db_middleware import DbSessionMiddleware
from src.bot.middlewares.logging_middleware import StateLoggingMiddleware
from src.db.base import async_session_factory, Base
from src.db import get_async_engine, init_models
from src.core.config import get_settings
from loguru import logger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger.info("Starting Group Info button test")

# Get settings
settings = get_settings()
BOT_TOKEN = os.environ.get("BOT_TOKEN", settings.BOT_TOKEN)

async def handle_group_info_test(message: types.Message):
    """Special test handler for the Group Info button."""
    logger.info(f"Group Info button test handler called by user {message.from_user.id}")
    
    # Get the session from middleware data
    session = message.bot.get("session", None)
    
    if session:
        logger.info(f"Session is available: {type(session)}")
        await message.answer("✅ Session is available in test handler!")
    else:
        logger.error("Session is not available in test handler")
        await message.answer("❌ Session is not available in test handler!")
    
    await message.answer("Test completed. You can continue using the bot normally.")

async def main():
    """Set up and run a minimal test bot."""
    # Initialize bot and dispatcher
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Initialize database
    try:
        engine = get_async_engine(settings.db_url)
        await init_models(engine)
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return
    
    # Register middleware
    logger.info(f"Registering DbSessionMiddleware with factory of type: {type(async_session_factory)}")
    dp.update.middleware(DbSessionMiddleware(async_session_factory))
    dp.update.middleware(StateLoggingMiddleware())
    
    # Register test handler
    dp.message.register(handle_group_info_test, lambda msg: msg.text == "Test Group Info")
    
    # Delete webhook in case it's set
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Start polling
    logger.info("Starting test bot polling")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main()) 