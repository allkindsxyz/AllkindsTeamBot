from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from loguru import logger

class DbSessionMiddleware(BaseMiddleware):
    """Middleware to inject SQLAlchemy AsyncSession into handlers."""
    def __init__(self, session_pool: async_sessionmaker[AsyncSession]):
        super().__init__()
        self.session_pool = session_pool
        logger.info("DbSessionMiddleware initialized.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Execute middleware."""
        logger.debug(f"DbSessionMiddleware entering __call__ for update type: {type(event)}")
        session: AsyncSession | None = None # Define session variable outside the block
        try:
            logger.debug("Attempting to acquire session from pool...")
            async with self.session_pool() as session:
                logger.debug(f"Database session {id(session)} acquired.")
                data["session"] = session # Inject session into handler data
                logger.debug("Calling next handler...")
                result = await handler(event, data)
                logger.debug("Next handler finished.")
        except Exception as e:
            logger.exception("DbSessionMiddleware caught an exception")
            # Ensure session is rolled back if acquired and an error occurred
            # Although async with should handle this, explicit rollback might be useful for debugging
            if session:
                 try:
                     await session.rollback()
                     logger.warning("Session rolled back due to exception in handler or middleware.")
                 except Exception as rollback_exc:
                     logger.error(f"Failed to rollback session during exception handling: {rollback_exc}")
            raise # Re-raise the exception after logging
        finally:
            # Session is automatically closed by the async context manager
            logger.debug(f"DbSessionMiddleware exiting __call__. Session {id(session) if session else 'N/A'} closed implicitly.")
        
        return result 