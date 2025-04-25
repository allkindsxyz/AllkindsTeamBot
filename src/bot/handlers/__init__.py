from aiogram import Dispatcher

from src.bot.handlers import start, questions, matches


def register_handlers(dp: Dispatcher) -> None:
    """Register all handlers."""
    start.register_handlers(dp)
    questions.register_handlers(dp)
    matches.register_handlers(dp) 