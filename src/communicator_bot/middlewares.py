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
    """Middleware to inject database session into handler."""
    
    def __init__(self):
        """Initialize the middleware."""
        # Use the same database configuration as the main bot
        self.settings = get_settings()
        
        # RAILWAY_ENVIRONMENT will be set to 'production' in Railway
        is_production = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
        
        # Get database URL from environment - SAME AS MAIN BOT
        db_url = os.environ.get("DATABASE_URL", self.settings.db_url)
        logger.info(f"Original database URL (starts with): {db_url[:15] if db_url else 'None'}...")
        
        # Process the database URL - same logic as the main bot
        if db_url.startswith('postgres://'):
            # For asyncpg, replace postgres:// with postgresql+asyncpg://
            db_url = db_url.replace('postgres://', 'postgresql+asyncpg://', 1)
            logger.info(f"Converted postgres:// to postgresql+asyncpg:// for compatibility")
        elif db_url.startswith('postgresql://'):
            # Replace postgresql:// with postgresql+asyncpg://
            db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
            logger.info(f"Converted postgresql:// to postgresql+asyncpg:// for compatibility")
        
        # Enforce PostgreSQL in production
        if is_production and not ('postgresql+asyncpg' in db_url):
            logger.error(f"Production environment requires PostgreSQL! Current URL type: {db_url.split('://')[0]}")
            logger.warning("Attempting to recover by enforcing PostgreSQL URL format")
            # Try to force it to use PostgreSQL
            if 'sqlite' in db_url:
                # Get from environment again as a last resort
                fallback_url = os.environ.get("DATABASE_URL")
                if fallback_url and ('postgres' in fallback_url):
                    logger.info(f"Recovered PostgreSQL URL from environment")
                    # Process it again to ensure proper format
                    if fallback_url.startswith('postgres://'):
                        db_url = fallback_url.replace('postgres://', 'postgresql+asyncpg://', 1)
                    elif fallback_url.startswith('postgresql://'):
                        db_url = fallback_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
                    else:
                        db_url = fallback_url
                else:
                    logger.critical("CRITICAL: Cannot find PostgreSQL URL in production environment!")
                    # Don't use SQLite in production - this will cause the bot to fail but that's better
                    # than silently using SQLite and having data inconsistency
                    raise ValueError("PostgreSQL URL required in production environment")
        
        logger.info(f"Using database URL (starts with): {db_url[:15] if db_url else 'None'}...")
        
        # Create connection arguments
        connect_args = {
        "command_timeout": 30,  # Command execution timeout
        "timeout": 30,  # Increased connection timeout,
        "statement_cache_size": 0  # Disable statement cache
    }
        if 'postgresql' in db_url or 'postgres' in db_url:
            # PostgreSQL specific connect args for asyncpg
            connect_args = {
                "timeout": 30,              # Increased connection timeout to 30 seconds
                "command_timeout": 30,      # Added command timeout of 30 seconds
                "server_settings": {
                    "application_name": "allkinds-communicator",
        "statement_cache_size": 0  # Disable statement cache
    },
                "statement_cache_size": 0   # Disable statement cache for more reliable connections
            }
            logger.info("Using PostgreSQL connection settings with asyncpg driver")
        else:
            logger.warning(f"Not using PostgreSQL: {db_url.split('://')[0]}")
        
        # Create the engine with improved configuration for Railway
        try:
            self.engine = create_async_engine(
                db_url,
                echo=False,
                future=True,
                pool_pre_ping=True,
                pool_recycle=180,                 # Recycle connections more frequently (3 minutes),          # Recycle connections more frequently (3 minutes)
                pool_timeout=45,                  # Increased timeout for cloud environments,           # Increased timeout for cloud environments
                pool_size=10,                     # Increased pool size for better concurrency,              # Increased pool size for better concurrency
                max_overflow=20,           # Allow more overflow connections for spikes,           # Allow more overflow connections
                connect_args=connect_args
            )
            
            self.session_factory = async_sessionmaker(
                self.engine,
                expire_on_commit=False,
                autoflush=False
            )
            
            logger.info(f"Database engine created successfully: {db_url.split('://')[0]}")
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise
    
    async def __call__(
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


class LoggingMiddleware(BaseMiddleware):
    """Middleware to log all updates."""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Log updates before and after handling."""
        update = data.get("event_update", Update(update_id=0))
        
        # Get user info if available
        user_id = None
        chat_id = None
        
        if update.message:
            user_id = update.message.from_user.id if update.message.from_user else None
            chat_id = update.message.chat.id
        elif update.callback_query:
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
            chat_id = update.callback_query.message.chat.id if update.callback_query.message else None
        
        # Log start of handling
        logger.info(f"Handling update {update.update_id} from user {user_id} in chat {chat_id}")
        
        # Call the handler
        result = await handler(event, data)
        
        # Log end of handling
        logger.info(f"Finished handling update {update.update_id}")
        
        return result


class ChatActivityMiddleware(BaseMiddleware):
    """Middleware to update chat activity timestamps."""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Update last activity timestamp for active chats."""
        update = data.get("event_update", Update(update_id=0))
        session = data.get("session")
        
        if not session:
            return await handler(event, data)
        
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