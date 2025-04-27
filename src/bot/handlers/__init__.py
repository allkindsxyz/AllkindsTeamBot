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