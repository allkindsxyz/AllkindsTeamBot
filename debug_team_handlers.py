#!/usr/bin/env python3
"""
Script to debug team/group handlers to identify overlapping registered handlers
"""

import logging
import sys
import os
import asyncio
import inspect
from pprint import pformat
from dotenv import load_dotenv
from aiogram import Dispatcher, Bot, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.storage.memory import MemoryStorage

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s',
                   handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# Get bot token from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("No BOT_TOKEN found in environment variables")
    sys.exit(1)

async def debug_dispatcher_handlers(dp: Dispatcher):
    """Examine all registered handlers in the dispatcher and log them."""
    logger.info("=== EXAMINING REGISTERED HANDLERS ===")
    
    message_handlers = 0
    callback_handlers = 0
    
    # Look at the message handlers
    logger.info("== MESSAGE HANDLERS ==")
    for handler in dp.message.handlers:
        message_handlers += 1
        try:
            # Get the handler function name
            handler_name = handler.callback.__name__ if hasattr(handler.callback, '__name__') else str(handler.callback)
            
            # Inspect the filter
            filter_str = str(handler.filter) if handler.filter else "No filter"
            
            # Log handler info
            logger.info(f"Handler #{message_handlers}: {handler_name}")
            logger.info(f"  Filter: {filter_str}")
            logger.info(f"  Module: {inspect.getmodule(handler.callback).__name__ if inspect.isfunction(handler.callback) else 'unknown'}")
            
            # Special handling for Team button handlers
            if "Team" in filter_str:
                logger.info(f"  ⚠️ TEAM HANDLER DETECTED: {handler_name}")
                logger.info(f"  Filter details: {filter_str}")
            
            logger.info("-" * 50)
        except Exception as e:
            logger.error(f"Error inspecting handler: {e}")
    
    # Look at the callback query handlers
    logger.info("\n== CALLBACK QUERY HANDLERS ==")
    for handler in dp.callback_query.handlers:
        callback_handlers += 1
        try:
            # Get the handler function name
            handler_name = handler.callback.__name__ if hasattr(handler.callback, '__name__') else str(handler.callback)
            
            # Inspect the filter
            filter_str = str(handler.filter) if handler.filter else "No filter"
            
            # Log handler info
            logger.info(f"Handler #{callback_handlers}: {handler_name}")
            logger.info(f"  Filter: {filter_str}")
            logger.info(f"  Module: {inspect.getmodule(handler.callback).__name__ if inspect.isfunction(handler.callback) else 'unknown'}")
            
            # Special handling for team-related callbacks
            if "team" in filter_str.lower():
                logger.info(f"  ⚠️ TEAM CALLBACK DETECTED: {handler_name}")
                logger.info(f"  Filter details: {filter_str}")
            
            logger.info("-" * 50)
        except Exception as e:
            logger.error(f"Error inspecting handler: {e}")
    
    logger.info(f"Total handlers: {message_handlers + callback_handlers} (Message: {message_handlers}, Callback: {callback_handlers})")
    logger.info("=== END OF HANDLER EXAMINATION ===")

async def setup_mock_bot():
    """Set up a mock bot with full handler registration for debugging."""
    # Create bot instance
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    try:
        # Import the real handler registration functions
        from src.bot.handlers import register_handlers as register_all
        
        # Register all handlers
        logger.info("Registering all handlers from the application...")
        register_all(dp)
        logger.info("All handlers registered successfully")
        
        # Debug the registered handlers
        await debug_dispatcher_handlers(dp)
        
    except Exception as e:
        logger.error(f"Error setting up mock bot: {e}")
        logger.exception("Full traceback:")
    finally:
        # Close the bot session
        await bot.session.close()

async def main():
    """Main entry point for the debugging script."""
    logger.info("=== TEAM HANDLERS DEBUGGER ===")
    logger.info("This script analyzes registered handlers in the bot to identify multiple Team handlers")
    
    await setup_mock_bot()
    
    logger.info("Debug complete.")

if __name__ == "__main__":
    asyncio.run(main()) 