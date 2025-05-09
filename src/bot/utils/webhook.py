import logging
import os
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
import aiohttp
import asyncio
import requests
from src.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

async def reset_webhook(bot: Bot):
    """Reset the webhook with robust error handling and retries."""
    webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
    logger.info(f"Resetting webhook to: {settings.WEBHOOK_PATH}")
    
    # Check webhook mode from environment
    use_webhook = os.environ.get("USE_WEBHOOK", "false").lower() == "true"
    logger.info(f"Webhook mode is {'enabled' if use_webhook else 'disabled'}")
    
    # Simple retry mechanism
    max_tries = 5
    retry_delay = 1  # seconds
    
    # First try to get current webhook info
    try:
        webhook_info = await bot.get_webhook_info()
        logger.info(f"Current webhook info: URL={webhook_info.url}, PendingUpdates={webhook_info.pending_update_count}")
    except Exception as e:
        logger.warning(f"Could not get current webhook info: {e}")
    
    for attempt in range(max_tries):
        try:
            # First try using aiogram's built-in method
            try:
                logger.info("Deleting webhook using bot.delete_webhook()...")
                await bot.delete_webhook(drop_pending_updates=True)
                logger.info("Successfully deleted existing webhook using aiogram")
            except TelegramAPIError as e:
                logger.warning(f"Error deleting webhook with aiogram: {e}")
                # Try alternative method with direct HTTP request
                logger.info("Trying direct HTTP request to delete webhook...")
                try:
                    # Try with requests library (synchronous)
                    response = requests.get(
                        f"https://api.telegram.org/bot{bot.token}/deleteWebhook?drop_pending_updates=true",
                        timeout=10
                    )
                    if response.status_code == 200 and response.json().get("ok"):
                        logger.info("Successfully deleted webhook using direct HTTP request")
                    else:
                        logger.warning(f"Failed to delete webhook with direct request: {response.json()}")
                except Exception as req_e:
                    logger.error(f"Error with direct webhook deletion request: {req_e}")
            
            # Then verify webhook was deleted
            try:
                webhook_info = await bot.get_webhook_info()
                if webhook_info.url:
                    logger.warning(f"Webhook still exists after deletion attempt: {webhook_info.url}")
                else:
                    logger.info("Verified webhook is now empty")
            except Exception as e:
                logger.warning(f"Could not verify webhook deletion: {e}")
            
            # Then set the new webhook if needed
            if use_webhook:
                try:
                    logger.info(f"Setting webhook to {webhook_url}...")
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
                        if attempt < max_tries - 1:
                            logger.info(f"Retrying webhook reset (attempt {attempt + 1}/{max_tries})...")
                            await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                            continue
                        return False
                except TelegramAPIError as e:
                    logger.error(f"Error setting webhook: {e}")
                    if attempt < max_tries - 1:
                        logger.info(f"Retrying webhook reset (attempt {attempt + 1}/{max_tries})...")
                        await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                        continue
                    return False
            else:
                logger.info("Webhook mode is disabled, running in polling mode")
                return True
                
            # If we get here, everything succeeded
            return True
            
        except (TelegramAPIError, aiohttp.ClientError) as e:
            logger.error(f"Error during webhook reset (attempt {attempt + 1}/{max_tries}): {e}")
            if attempt < max_tries - 1:
                logger.info(f"Retrying webhook reset in {retry_delay * (2 ** attempt)} seconds...")
                await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
            else:
                logger.error(f"Failed to reset webhook after {max_tries} attempts")
                return False
    
    return False

async def verify_bot_token(bot: Bot):
    """Verify that the bot token is valid by getting the bot's info."""
    try:
        bot_info = await bot.get_me()
        logger.info(f"Bot verification successful: @{bot_info.username} ({bot_info.id})")
        return True
    except TelegramAPIError as e:
        logger.error(f"Bot token verification failed: {e}")
        return False
