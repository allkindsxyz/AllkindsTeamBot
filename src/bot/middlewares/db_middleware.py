from typing import Any, Awaitable, Callable, Dict, Union, Tuple, Optional, TypeVar, cast
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import logging
import inspect
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, Update
from aiogram.dispatcher.flags import get_flag
from loguru import logger

# Type alias for handler
Handler = Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]]
SessionPool = async_sessionmaker[AsyncSession]  # Type annotation for the session pool

class DbSessionMiddleware(BaseMiddleware):
    """Middleware to provide database session to handlers."""
    
    def __init__(self, session_pool: SessionPool):
        """Initialize middleware with session pool.
        
        Args:
            session_pool: SQLAlchemy async session factory
        """
        if not isinstance(session_pool, async_sessionmaker):
            logger.critical(
                f"DbSessionMiddleware expects async_sessionmaker as session_pool, got {type(session_pool)}"
            )
            raise TypeError("session_pool must be an async_sessionmaker instance")
            
        self.session_pool = session_pool
        logger.info("DbSessionMiddleware initialized with session pool")
    
    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Provide database session to handler.
        
        This creates a new session for each request and closes it after the handler is done.
        The session is passed to the handler as a parameter.
        """
        # Log the handler name for debugging
        handler_name = handler.__name__ if hasattr(handler, "__name__") else str(handler)
        logger.debug(f"Processing {type(event).__name__} with handler: {handler_name}")
        
        if get_flag(data, "skip_db"):
            # Skip DB session creation if flag is set
            logger.debug("Skipping DB session creation due to flag")
            return await handler(event, data)
        
        # Check if handler expects a session parameter
        try:
            handler_sig = inspect.signature(handler)
            expects_session = "session" in handler_sig.parameters
            logger.debug(f"Handler {'expects' if expects_session else 'does not expect'} session parameter")
        except Exception as e:
            logger.warning(f"Could not inspect handler signature: {e}")
            expects_session = True  # Assume it needs session to be safe
        
        # Create a new database session
        try:
            session = self.session_pool()
            logger.debug(f"Created new database session for {type(event).__name__}")
            
            # Add session to handler data
            data["session"] = session
            
            try:
                # Call the handler with the session
                result = await handler(event, data)
                # Commit the session if needed (if not already committed by the handler)
                if session.is_active:
                    logger.debug("Committing session after handler execution")
                    await session.commit()
                return result
            except Exception as e:
                # Rollback the session in case of error
                if session.is_active:
                    logger.warning(f"Rolling back session due to error: {e}")
                    await session.rollback()
                # Add detail about the event type that caused the error
                logger.error(f"Error in handler for {type(event).__name__}: {e}")
                raise
            finally:
                # Close the session
                logger.debug("Closing database session")
                await session.close()
        except Exception as e:
            logger.error(f"Error in DB middleware: {e}")
            # Let the error propagate but log it
            raise 