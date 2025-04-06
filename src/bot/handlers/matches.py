from aiogram import Dispatcher, types
from aiogram.filters import Command
from loguru import logger


async def cmd_matches(message: types.Message) -> None:
    """Handle /matches command."""
    user = message.from_user
    logger.info(f"User {user.id} requested matches")
    
    # TODO: Implement match fetching from database
    await message.answer("Matches feature coming soon! 🚀")


def register_handlers(dp: Dispatcher) -> None:
    """Register matches command handlers."""
    dp.message.register(cmd_matches, Command("matches")) 