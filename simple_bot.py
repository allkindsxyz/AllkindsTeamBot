#!/usr/bin/env python3
"""
Simplified bot implementation for Allkinds.
This bot is a stripped-down version that only includes essential functionality
to ensure reliable operation.
"""

import os
import sys
import asyncio
import logging
import signal
import traceback
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('simple_bot.log')
    ]
)
logger = logging.getLogger(__name__)

try:
    # Import aiogram
    from aiogram import Bot, Dispatcher, types, F
    from aiogram.filters import Command
    from aiogram.enums import ParseMode
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.context import FSMContext
    from aiogram.types import (
        KeyboardButton, ReplyKeyboardMarkup, 
        InlineKeyboardButton, InlineKeyboardMarkup,
        Message, CallbackQuery
    )
except ImportError as e:
    logger.error(f"Failed to import required package: {e}")
    logger.error("Make sure you have installed all dependencies with: pip install -r requirements.txt")
    sys.exit(1)

# Load environment from .env file
load_dotenv()

# Get environment variables
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('MAIN_BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("No bot token found in environment variables!")
    sys.exit(1)

logger.info(f"Bot token found: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:]}")

# Set up global shutdown event
shutdown_event = asyncio.Event()

# Helper functions for keyboards
def get_start_menu_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for start welcome menu."""
    keyboard = [
        [
            InlineKeyboardButton(text="👥 Create a Team", callback_data="create_team"),
            InlineKeyboardButton(text="🔍 Join a Team", callback_data="join_team"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Create a reply keyboard with main options."""
    buttons = [
        [KeyboardButton(text="Find Match"), KeyboardButton(text="Add Question")],
        [KeyboardButton(text="Group Info"), KeyboardButton(text="Instructions")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"Received /start command from user {user.id} ({user.first_name})")
    
    await update.message.reply_text(f"Hi {user.first_name}! I'm a simple debugging bot. I'm responding, which means I'm working correctly!")
    logger.info(f"Sent start reply to user {user.id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    user = update.effective_user
    logger.info(f"Received /help command from user {user.id}")
    
    await update.message.reply_text("This is a simple bot for debugging. I only respond to /start and /help commands.")
    logger.info(f"Sent help reply to user {user.id}")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo any other message the user sends."""
    user = update.effective_user
    logger.info(f"Received message from user {user.id}: {update.message.text}")
    
    await update.message.reply_text("I'm a simple debugging bot. Please use /start or /help.")
    logger.info(f"Sent echo reply to user {user.id}")

# Callback handlers
async def on_create_team(callback: CallbackQuery, state: FSMContext):
    """Handle create team button."""
    await callback.answer()
    await callback.message.answer("Creating a team functionality is coming soon!")

async def on_join_team(callback: CallbackQuery, state: FSMContext):
    """Handle join team button."""
    await callback.answer()
    await callback.message.answer("Joining a team functionality is coming soon!")

# Message handlers
async def handle_find_match(message: Message):
    """Handle 'Find Match' button."""
    await message.answer("Find Match functionality is coming soon!")

async def handle_add_question(message: Message):
    """Handle 'Add Question' button."""
    await message.answer("Add Question functionality is coming soon!")

async def handle_group_info(message: Message):
    """Handle 'Group Info' button."""
    await message.answer("Group Info functionality is coming soon!")

async def handle_instructions(message: Message):
    """Handle 'Instructions' button."""
    instructions_text = (
        "📋 <b>Instructions:</b>\n\n"
        "1. Create or join a team to get started\n"
        "2. Answer questions to define your values\n"
        "3. Find matches with people who share similar values\n\n"
        "Use the buttons below to navigate."
    )
    await message.answer(instructions_text, parse_mode=ParseMode.HTML)

async def echo_handler(message: Message):
    """Handle all other messages."""
    # Log the message
    logger.info(f"Received message: {message.text}")
    
    # Show the main menu options
    await message.answer("Please use the buttons or commands to interact with the bot.", 
                      reply_markup=get_reply_keyboard())

async def on_shutdown(dp: Dispatcher, bot: Bot):
    """Handle shutdown processes."""
    logger.info("Shutting down the bot")
    
    # Close storage
    await dp.fsm.storage.close()
    
    # Close bot session
    await bot.session.close()
    
    logger.info("Bot shutdown complete")

async def main():
    """Initialize and start the bot."""
    logger.info("Starting simplified Allkinds bot...")
    logger.info(f"Current environment: {os.environ.get('RAILWAY_ENVIRONMENT', 'local')}")
    
    try:
        # Set up signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}")
            shutdown_event.set()
        
        # Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, signal_handler)
        
        # Initialize the bot with an AiohttpSession for better control
        bot_session = AiohttpSession()
        bot = Bot(token=BOT_TOKEN, session=bot_session, 
                  default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        
        # Configuration
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Register command handlers
        dp.message.register(start_command, Command("start"))
        dp.message.register(help_command, Command("help"))
        
        # Register callback handlers
        dp.callback_query.register(on_create_team, F.data == "create_team")
        dp.callback_query.register(on_join_team, F.data == "join_team")
        
        # Register message handlers
        dp.message.register(handle_find_match, F.text == "Find Match")
        dp.message.register(handle_add_question, F.text == "Add Question")
        dp.message.register(handle_group_info, F.text == "Group Info")
        dp.message.register(handle_instructions, F.text == "Instructions")
        
        # Register catch-all handler (must be last)
        dp.message.register(echo_handler)
        
        # Make sure webhook is removed
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook removed, ready for polling")
        
        # Log bot information
        bot_info = await bot.get_me()
        logger.info(f"Bot started: @{bot_info.username}")
        
        # Start polling
        logger.info("Starting polling...")
        polling_task = asyncio.create_task(
            dp.start_polling(bot, skip_updates=True)
        )
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Cancel polling task
        polling_task.cancel()
        
        # Wait for task to be cancelled
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
            
        # Run shutdown processes
        await on_shutdown(dp, bot)
        
    except Exception as e:
        logger.error(f"Critical error: {e}")
        traceback.print_exc()
        
        # Try to close resources
        if 'bot' in locals():
            try:
                await bot.session.close()
            except:
                pass
    
    logger.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc() 