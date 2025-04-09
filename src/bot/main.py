from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramConflictError
from loguru import logger
import asyncio
import time

# from src.bot.config import bot_settings # No longer needed
from src.core.config import get_settings # Import main settings
from src.bot.handlers import register_handlers
from src.bot.middlewares import DbSessionMiddleware # Import middleware
from src.db.base import async_session_factory # Import session factory

settings = get_settings()


async def start_bot() -> None:
    """Initialize and start the bot."""
    bot = Bot(
        token=settings.BOT_TOKEN, # Use settings.BOT_TOKEN
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Use memory storage for FSM (in production, use Redis or other persistent storage)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Setup middleware
    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_factory))

    # Register handlers
    register_handlers(dp)

    try:
        # Use settings.ADMIN_IDS directly as it's now a list
        logger.info(f"Starting bot with admin IDs: {settings.ADMIN_IDS}") 
        
        # Configure polling parameters with conflict handling
        max_retries = 5
        retry_count = 0
        retry_delay = 1  # seconds
        max_retry_delay = 5  # maximum seconds between retries
        
        while True:
            try:
                # Start polling with delete_webhook=True and allow_deleted_updates=True
                # This enables receiving updates about deleted messages
                await dp.start_polling(
                    bot, 
                    delete_webhook=True,
                    allowed_updates=["message", "callback_query"]
                )
                break  # Exit the loop if polling starts successfully
                
            except TelegramConflictError as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(f"Failed to start bot after {max_retries} retries: {e}")
                    raise
                
                # Use exponential backoff, but cap at max_retry_delay
                current_delay = min(retry_delay * (1.5 ** retry_count), max_retry_delay)
                logger.warning(f"Telegram conflict detected (attempt {retry_count}/{max_retries}). "
                              f"Waiting {current_delay:.2f} seconds...")
                await asyncio.sleep(current_delay)
                
    except Exception as e:
        logger.exception(f"Error starting bot: {e}")
        raise
    finally:
        await bot.session.close() 

# --- Add entry point execution block --- 
if __name__ == "__main__":
    # Configure logging (optional, adjust as needed)
    logger.add("main_bot.log", rotation="1 week", level="INFO") 
    logger.info("Initializing main bot...")
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.exception("Main bot exited due to an error:") 