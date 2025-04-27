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
        session = None
        try:
            # Create a new session from the factory
            logger.debug("Attempting to acquire session from pool...")
            session = self.session_pool()
            logger.debug(f"Database session {id(session)} acquired.")
            
            # Add the session to the data dictionary
            data["session"] = session
            
            # Start a new transaction
            async with session:
                logger.debug("Calling next handler within session context...")
                result = await handler(event, data)
                logger.debug("Next handler finished.")
                return result
        except Exception as e:
            logger.exception(f"DbSessionMiddleware caught an exception: {e}")
            # Ensure session is rolled back if acquired and an error occurred
            if session:
                 try:
                     await session.rollback()
                     logger.warning("Session rolled back due to exception in handler or middleware.")
                 except Exception as rollback_exc:
                     logger.error(f"Failed to rollback session during exception handling: {rollback_exc}")
            raise # Re-raise the exception after logging
        finally:
            # Explicitly close the session if it was created
            if session:
                try:
                    await session.close()
                    logger.debug(f"Session {id(session)} explicitly closed.")
                except Exception as close_exc:
                    logger.error(f"Failed to close session: {close_exc}")
            logger.debug(f"DbSessionMiddleware exiting __call__.") 