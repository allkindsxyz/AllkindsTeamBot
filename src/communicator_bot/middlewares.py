from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from datetime import datetime, timedelta
import os

from src.core.config import get_settings
from src.db.models import AnonymousChatSession
from src.db.repositories.user import user_repo


class DatabaseMiddleware(BaseMiddleware):
    \"\"\"Middleware for handling database connections with proper error handling and timeouts.\"\"\"
    
    def __init__(self):
        self.session_pool = {}
        self.retry_attempts = 3
        self.session_timeout = 30  # seconds
        logger.info("Database middleware initialized with retry logic")
        super().__init__()
    
    async def __call__
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Inject database session into handler."""
        session = None
        try:
            session = self.session_factory()
            logger.debug(f"Created database session {id(session)}")
            data["session"] = session
            
            # We use a nested approach with context manager to handle transaction management
            async with session:
                logger.debug("Executing handler within database session context")
                result = await handler(event, data)
                logger.debug("Handler execution complete")
                return result
        except Exception as e:
            logger.error(f"Error in database middleware: {e}")
            # If we have a session and it's still active, try to rollback
            if session:
                try:
                    await session.rollback()
                    logger.info("Session rolled back after error")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback session: {rollback_error}")
            raise
        finally:
            if session:
                try:
                    await session.close()
                    logger.debug(f"Closed database session {id(session)}")
                except Exception as close_error:
                    logger.error(f"Failed to close database session: {close_error}")


class LoggingMiddleware(BaseMiddleware:
        import time
        import asyncio
        from sqlalchemy.exc import SQLAlchemyError
        
        # Create a new session for this request with retry logic
        session = None
        engine = None
        
        # Store original exception if we need to re-raise later
        original_exc = None
        
        for attempt in range(self.retry_attempts):
            try:
                # Get or create engine with proper error handling
                try:
                    engine = get_async_engine()
                except Exception as e:
                    logger.error(f"Failed to create database engine: {e}")
                    raise
                
                # Create session with timeout
                async_session = sessionmaker(
                    engine, expire_on_commit=False, class_=AsyncSession
                )
                
                # Create session with timeout protection
                try:
                    session_task = asyncio.create_task(async_session())
                    session = await asyncio.wait_for(session_task, timeout=self.session_timeout)
                    
                    # Add session to the data dict
                    data["session"] = session
                    
                    # Process handler
                    result = await handler(event, data)
                    
                    # Close session
                    await session.close()
                    return result
                    
                except asyncio.TimeoutError:
                    logger.error(f"Session creation timed out after {self.session_timeout}s (attempt {attempt+1}/{self.retry_attempts})")
                    if session:
                        await session.close()
                    raise
                    
            except asyncio.exceptions.CancelledError as e:
                logger.warning(f"Database connection cancelled (attempt {attempt+1}/{self.retry_attempts}): {e}")
                original_exc = e
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
            except SQLAlchemyError as e:
                logger.error(f"Database error (attempt {attempt+1}/{self.retry_attempts}): {e}")
                original_exc = e
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
            except Exception as e:
                logger.error(f"Unexpected error in database middleware (attempt {attempt+1}/{self.retry_attempts}): {e}")
                original_exc = e
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
        # All retries failed
        logger.critical(f"All database connection attempts failed after {self.retry_attempts} retries")
        
        # In production, we should handle this gracefully for the user
        try:
            if isinstance(event, types.Message) and event.text == "/start":
                # Special handling for /start command to avoid bad user experience
                await event.answer(
                    "I'm currently experiencing technical difficulties connecting to the database. "
                    "Please try again in a few minutes."
                )
            return None  # Return None to indicate middleware handled the response
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
            
        # Re-raise the original exception
        if original_exc:
            raise original_exc
        raise RuntimeError("Failed to establish database connection")
        
        # Get user info if available
        user_id = None
        
        if update.message:
            user_id = update.message.from_user.id if update.message.from_user else None
        elif update.callback_query:
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
        
        # Update activity timestamp for user's active chats
        if user_id and session:
            try:
                # Get user from DB
                user = await user_repo.get_by_telegram_id(session, user_id)
                if user:
                    # Find active chat sessions for this user
                    from sqlalchemy import select, or_, and_
                    query = select(AnonymousChatSession).where(
                        and_(
                            or_(
                                AnonymousChatSession.initiator_id == user.id,
                                AnonymousChatSession.recipient_id == user.id
                            ),
                            AnonymousChatSession.status == "active"
                        )
                    )
                    result = await session.execute(query)
                    chat_sessions = result.scalars().all()
                    
                    # Update last activity
                    for chat in chat_sessions:
                        chat.last_activity = datetime.utcnow()
                    
                    await session.commit()
            except Exception as e:
                logger.warning(f"Failed to update chat activity: {e}")
        
        return await handler(event, data)


class BotMiddleware(BaseMiddleware):
    """Middleware to inject the bot instance into handler calls."""
    
    def __init__(self, bot_instance):
        """Initialize with a bot instance."""
        self.bot = bot_instance
        super().__init__()
        
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Inject bot instance into handler call."""
        data["bot"] = self.bot
        return await handler(event, data) 