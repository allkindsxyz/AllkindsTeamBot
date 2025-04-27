from typing import Any, Awaitable, Callable, Dict
import warnings

# DEPRECATION WARNING
warnings.warn(
    "This file (src/bot/middlewares/db.py) is deprecated and should not be used. "
    "Use src/bot/middlewares/db_middleware.py instead.",
    DeprecationWarning,
    stacklevel=2
)

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker
from loguru import logger


class DbSessionMiddleware(BaseMiddleware):
    """
    DEPRECATED: This middleware is deprecated. Use the implementation in db_middleware.py instead.
    Middleware to inject database session into handlers.
    """

    def __init__(self, session_pool: async_sessionmaker):
        super().__init__()
        self.session_pool = session_pool
        logger.warning("DEPRECATED: Using old DbSessionMiddleware implementation from db.py. This will be removed in the future.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Forward to the new implementation for compatibility
        from src.bot.middlewares.db_middleware import DbSessionMiddleware
        middleware = DbSessionMiddleware(self.session_pool)
        return await middleware(handler, event, data) 