import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
import aiohttp
import backoff
from src.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

@backoff.on_exception(backoff.expo, (TelegramAPIError, aiohttp.ClientError), max_tries=5)
async def reset_webhook(bot: Bot):
    """Reset the webhook with robust error handling and retries."""
    webhook_url = f"{settings.WEBHOOK_HOST}/bot/webhook"
    logger.info(f"Resetting webhook to: {webhook_url}")
    
    # First try to delete the current webhook
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Successfully deleted existing webhook")
    except TelegramAPIError as e:
        logger.warning(f"Error deleting webhook: {e}")
        # Continue anyway as we'll try to set the new webhook
    
    # Then set the new webhook if needed
    if settings.USE_WEBHOOK:
        try:
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "my_chat_member", 
                                "chat_member", "chat_join_request"]
            )
            # Verify the webhook was set correctly
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url == webhook_url:
                logger.info(f"Successfully set webhook to {webhook_url}")
                return True
            else:
                logger.warning(f"Webhook URL mismatch: expected {webhook_url}, got {webhook_info.url}")
                return False
        except TelegramAPIError as e:
            logger.error(f"Error setting webhook: {e}")
            return False
    else:
        logger.info("Webhook mode is disabled, running in polling mode")
        return True

async def verify_bot_token(bot: Bot):
    """Verify that the bot token is valid by getting the bot's info."""
    try:
        bot_info = await bot.get_me()
        logger.info(f"Bot verification successful: @{bot_info.username} ({bot_info.id})")
        return True
    except TelegramAPIError as e:
        logger.error(f"Bot token verification failed: {e}")
        return False
