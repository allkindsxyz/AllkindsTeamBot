from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger
import asyncio
import os
import signal
import sys
from dotenv import load_dotenv

from src.communicator_bot.handlers import register_handlers
from src.core.config import get_settings

# Load env variables directly from .env file
load_dotenv()

# Try to get token from environment directly first, then fallback to settings
COMMUNICATOR_BOT_TOKEN = os.getenv("COMMUNICATOR_BOT_TOKEN")
if not COMMUNICATOR_BOT_TOKEN:
    # Fallback to settings
    settings = get_settings()
    COMMUNICATOR_BOT_TOKEN = settings.COMMUNICATOR_BOT_TOKEN
    logger.info("Token loaded from settings")
else:
    logger.info("Token loaded directly from environment")

# Log token first few characters for debugging
if COMMUNICATOR_BOT_TOKEN:
    logger.info(f"Token starts with: {COMMUNICATOR_BOT_TOKEN[:5]}...")
else:
    logger.error("No token found!")

# Global variables for clean shutdown
bot = None
dp = None
should_exit = False

async def shutdown(signal_name=None):
    """Shutdown the bot gracefully."""
    global bot
    
    if signal_name:
        logger.info(f"Received {signal_name}, shutting down...")
    
    # Close bot session properly
    if bot:
        logger.info("Closing bot connection...")
        await bot.session.close()
    
    # Set the exit flag
    global should_exit
    should_exit = True
    
    logger.info("Communicator bot stopped.")

async def start_communicator_bot() -> None:
    """Initialize and start the communicator bot."""
    global bot, dp, should_exit
    
    if not COMMUNICATOR_BOT_TOKEN:
        logger.error("Communicator Bot Token not found!")
        return

    try:
        logger.info("Creating bot instance with token...")
        bot = Bot(
            token=COMMUNICATOR_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

        # Verify token by getting bot info
        try:
            bot_info = await bot.get_me()
            logger.info(f"Bot verification successful: @{bot_info.username}")
        except Exception as e:
            logger.error(f"Bot verification failed: {e}")
            return

        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        register_handlers(dp)

        logger.info("Starting communicator bot...")
        
        # Start polling with proper error handling
        while not should_exit:
            try:
                await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
            except Exception as e:
                if "Conflict:" in str(e):
                    logger.warning(f"Telegram conflict error: {e}")
                    logger.info("Waiting 10 seconds before reconnecting...")
                    await asyncio.sleep(10)
                else:
                    logger.exception(f"Error in bot polling: {e}")
                    if not should_exit:
                        logger.info("Waiting 5 seconds before reconnecting...")
                        await asyncio.sleep(5)
    except Exception as e:
        logger.exception(f"Error starting communicator bot: {e}")
    finally:
        await shutdown()

def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    for sig_name in ('SIGINT', 'SIGTERM'):
        asyncio.get_event_loop().add_signal_handler(
            getattr(signal, sig_name),
            lambda sig_name=sig_name: asyncio.create_task(shutdown(sig_name))
        )

if __name__ == '__main__':
    # Basic logger setup
    logger.add("communicator_bot.log", rotation="1 week")
    
    # Setup signal handlers
    setup_signal_handlers()
    
    try:
        asyncio.run(start_communicator_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}") 