from aiogram import Dispatcher, types
from aiogram.filters import Command
from loguru import logger
from src.core.diagnostics import track_command, IS_RAILWAY


@track_command
async def cmd_matches(message: types.Message) -> None:
    """Handle /matches command."""
    user = message.from_user
    logger.info(f"User {user.id} requested matches")
    
    # Enhanced error tracking for Railway
    if IS_RAILWAY:
        logger.info(f"RAILWAY: matches command called by user {user.id}")
        try:
            # TODO: Implement match fetching from database
            await message.answer("Matches feature coming soon! 🚀")
        except Exception as e:
            logger.error(f"RAILWAY ERROR in matches command: {str(e)}")
            # Send a user-friendly error message
            await message.answer("Sorry, there was an error processing your request. Please try again later.")
            raise
    else:
        # Original behavior for local development
        await message.answer("Matches feature coming soon! 🚀")


def register_handlers(dp: Dispatcher) -> None:
    """Register matches command handlers."""
    dp.message.register(cmd_matches, Command("matches")) 