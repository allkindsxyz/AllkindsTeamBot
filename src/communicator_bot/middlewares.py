from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from datetime import datetime, timedelta

from src.core.config import get_settings
from src.db.models import AnonymousChatSession
from src.db.repositories.user import user_repo


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to inject database session into handler."""
    
    def __init__(self):
        """Initialize the middleware."""
        self.settings = get_settings()
        self.engine = create_async_engine(
            self.settings.db_url,
            echo=False,
            future=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False
        )
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Inject database session into handler."""
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)


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