from aiogram import Dispatcher, types
from aiogram.filters import Command
from loguru import logger


async def cmd_questions(message: types.Message) -> None:
    """Handle /questions command."""
    user = message.from_user
    logger.info(f"User {user.id} requested questions")
    
    # TODO: Implement question fetching from database
    await message.answer("Questions feature coming soon! 🚀")


def register_handlers(dp: Dispatcher) -> None:
    """Register questions command handlers."""
    dp.message.register(cmd_questions, Command("questions")) 