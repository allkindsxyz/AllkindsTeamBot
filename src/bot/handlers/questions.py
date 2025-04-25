from aiogram import Dispatcher, types
from aiogram.filters import Command
from loguru import logger
from src.core.diagnostics import track_command, IS_RAILWAY


@track_command
async def cmd_questions(message: types.Message) -> None:
    """Handle /questions command."""
    user = message.from_user
    logger.info(f"User {user.id} requested questions")
    
    # Enhanced error tracking for Railway
    if IS_RAILWAY:
        logger.info(f"RAILWAY: questions command called by user {user.id}")
        try:
            # TODO: Implement match fetching from database
            await message.answer("Questions feature coming soon! 🚀")
        except Exception as e:
            logger.error(f"RAILWAY ERROR in questions command: {str(e)}")
            # Send a user-friendly error message
            await message.answer("Sorry, there was an error processing your request. Please try again later.")
            raise
    else:
        # Original behavior for local development
        await message.answer("Questions feature coming soon! 🚀")


def register_handlers(dp: Dispatcher) -> None:
    """Register matches command handlers."""
    dp.message.register(cmd_questions, Command("questions")) 