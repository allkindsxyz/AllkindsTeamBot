"""Bot handlers initialization module."""

import logging
from aiogram import Dispatcher, Router
from aiogram.filters import Command

# Import all handler modules
from src.bot.handlers.user import start, profile, help, questions
from src.bot.handlers.admin import broadcast, stats

logger = logging.getLogger(__name__)

def register_user_commands(dp: Dispatcher):
    """Register all user command handlers."""
    user_router = Router(name="user_commands")
    
    # Include all user command modules
    user_router.include_router(start.router)
    user_router.include_router(profile.router)
    user_router.include_router(help.router)
    user_router.include_router(questions.router)
    
    # Add the user router to the dispatcher
    dp.include_router(user_router)
    logger.info("Registered user commands")

def register_admin_commands(dp: Dispatcher):
    """Register all admin command handlers."""
    admin_router = Router(name="admin_commands")
    
    # Include all admin command modules
    admin_router.include_router(broadcast.router)
    admin_router.include_router(stats.router)
    
    # Add the admin router to the dispatcher
    dp.include_router(admin_router)
    logger.info("Registered admin commands")
