"""Bot handlers initialization module."""

from aiogram import Dispatcher
from src.bot.handlers import start, questions, matches, admin
from loguru import logger

def register_handlers(dp: Dispatcher) -> None:
    """Register all handlers for the bot."""
    logger.info("Registering handlers from all modules...")
    
    # Register handlers in a specific order to ensure proper handling
    # Start handlers must be registered first since they handle basic commands
    logger.info("Registering start handlers...")
    start.register_handlers(dp)
    
    logger.info("Registering questions handlers...")
    questions.register_handlers(dp)
    
    logger.info("Registering matches handlers...")
    matches.register_handlers(dp)
    
    logger.info("Registering admin handlers...")
    admin.register_handlers(dp)
    
    logger.info("All handlers registered successfully")

# For backward compatibility with any code that might expect these functions
def register_user_commands(dp: Dispatcher):
    """Register all user command handlers for compatibility."""
    logger.info("Using compatibility register_user_commands function")
    start.register_handlers(dp)
    questions.register_handlers(dp)
    matches.register_handlers(dp)

def register_admin_commands(dp: Dispatcher):
    """Register all admin command handlers for compatibility."""
    logger.info("Using compatibility register_admin_commands function")
    admin.register_handlers(dp)
