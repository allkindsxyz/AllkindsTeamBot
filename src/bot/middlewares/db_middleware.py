from typing import Callable, Dict, Any, Awaitable
import asyncio
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
            # Verify event loop is running
            if not asyncio.get_event_loop().is_running():
                logger.error("Event loop is not running, this should never happen!")
                return await handler(event, data)  # Continue without DB session
                
            # Create a new session from the factory
            logger.debug("Attempting to acquire session from pool...")
            session = self.session_pool()
            logger.debug(f"Database session {id(session)} acquired.")
            
            # Add the session to the data dictionary
            data["session"] = session
            
            # Start a new transaction
            async with session:
                logger.debug("Calling next handler within session context...")
                try:
                    result = await handler(event, data)
                    logger.debug("Next handler finished.")
                    return result
                except Exception as handler_exc:
                    logger.exception(f"Handler raised exception: {handler_exc}")
                    # Let the session context manager handle rollback
                    raise
        except asyncio.CancelledError:
            logger.warning("Operation cancelled during middleware execution")
            # Don't try to clean up, just propagate the cancellation
            raise
        except Exception as e:
            # Check specifically for "Event loop is closed" error
            if isinstance(e, RuntimeError) and "Event loop is closed" in str(e):
                logger.error("Event loop is closed error in DB middleware, cannot clean up properly")
                # Can't do async operations if event loop is closed
                if session:
                    # Try synchronous cleanup using _proxied
                    try:
                        session._proxied.close()  # pylint: disable=protected-access
                        logger.info("Used synchronous close on session after event loop closed")
                    except Exception as close_exc:
                        logger.error(f"Failed synchronous session cleanup: {close_exc}")
            else:
                logger.exception(f"DbSessionMiddleware caught an exception: {e}")
                # Ensure session is rolled back if acquired and an error occurred
                if session:
                    try:
                        await session.rollback()
                        logger.warning("Session rolled back due to exception in handler or middleware.")
                    except Exception as rollback_exc:
                        logger.error(f"Failed to rollback session during exception handling: {rollback_exc}")
            raise  # Re-raise the exception after logging
        finally:
            # Explicitly close the session if it was created
            if session:
                try:
                    # Only attempt to close if event loop is running
                    if asyncio.get_running_loop().is_running():
                        await session.close()
                        logger.debug(f"Session {id(session)} explicitly closed.")
                except RuntimeError as runtime_err:
                    if "no running event loop" in str(runtime_err) or "Event loop is closed" in str(runtime_err):
                        logger.warning("Could not close session asynchronously: event loop not available")
                        # Try synchronous close as a fallback
                        try:
                            session._proxied.close()  # pylint: disable=protected-access
                            logger.info("Used synchronous close as fallback")
                        except Exception as sync_close_exc:
                            logger.error(f"Failed synchronous session close fallback: {sync_close_exc}")
                    else:
                        logger.error(f"Runtime error in session cleanup: {runtime_err}")
                except Exception as close_exc:
                    logger.error(f"Failed to close session: {close_exc}")
            logger.debug(f"DbSessionMiddleware exiting __call__.") 