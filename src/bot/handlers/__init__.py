"""Bot handlers initialization module."""

from aiogram import Dispatcher, F
from src.bot.handlers import start, questions, matches, admin
from src.bot.handlers import team_creation, team_joining, question_display, question_interactions, load_answered_questions
from loguru import logger
from aiogram.filters import Command, StateFilter
from src.bot.states import TeamCreation # Import necessary state

def register_handlers(dp: Dispatcher) -> None:
    """Register all handlers for the bot."""
    
    logger.info("Registering handlers from all modules...")
    
    # --- Register /start command here (works in ANY state) --- 
    dp.message.register(start.cmd_start, Command(commands=["start"]), StateFilter('*'))
    logger.info("Registered cmd_start to work in any state")
    
    # Register handlers from each specialized module
    logger.info("Registering start handlers...")
    start.register_handlers(dp)
    
    logger.info("Registering team creation handlers...")
    team_creation.register_handlers(dp)
    
    logger.info("Registering team joining handlers...")
    team_joining.register_handlers(dp)
    
    logger.info("Registering questions handlers...")
    questions.register_handlers(dp)
    
    logger.info("Registering question interactions handlers...")
    question_interactions.register_handlers(dp)
    
    logger.info("Registering load answered questions handlers...")
    load_answered_questions.register_handlers(dp)
    
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
    matches.register_handlers(dp)

def register_admin_commands(dp: Dispatcher):
    """Register all admin command handlers for compatibility."""
    logger.info("Using compatibility register_admin_commands function")
    admin.register_handlers(dp) 