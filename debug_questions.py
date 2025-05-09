#!/usr/bin/env python3
"""
Debugging script for question handlers
"""

import logging
import sys
from aiogram import types, Dispatcher, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# Get bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("No BOT_TOKEN found in environment variables!")
    sys.exit(1)

# Create storage and dispatcher
storage = MemoryStorage()

async def log_message(message: types.Message):
    """Log received message details"""
    logger.info(f"Received message: {message.text}")
    logger.info(f"From user: {message.from_user.id} ({message.from_user.username})")
    logger.info(f"Message ends with '?': {message.text.strip().endswith('?')}")
    logger.info(f"Message ID: {message.message_id}")
    logger.info("=" * 50)
    
    # Send acknowledgment to user
    await message.answer("Debug: Your message was received and logged")

async def debug_handler(message: types.Message):
    """Debug handler for questions"""
    logger.info("⭐⭐⭐ QUESTION HANDLER TRIGGERED ⭐⭐⭐")
    await log_message(message)

async def main():
    """Set up the bot and start polling"""
    # Initialize the bot
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    
    # Register message logger for all messages
    dp.message.register(log_message)
    
    # Register debug handler for question-like messages
    menu_buttons = ['Find Match', 'Team', 'Instructions', '💬 Questions', '✨ Who vibes with you most now?', 
                   '➕ Add Question', '🏠 Team', '❓ Help']
    dp.message.register(
        debug_handler, 
        lambda m: m.text and m.text.strip().endswith("?") and m.text.strip() not in menu_buttons
    )
    
    # Start polling
    logger.info("Starting bot in debug mode...")
    await dp.start_polling(bot, skip_updates=False)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1) 