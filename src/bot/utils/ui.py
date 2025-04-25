from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

async def safe_delete_message(bot: Bot, chat_id: int, message_id: int | None):
    """Safely attempts to delete a message, handling None IDs and potential errors."""
    if not message_id:
        return # Nothing to delete

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Successfully deleted message {message_id} in chat {chat_id}")
    except TelegramBadRequest as e:
        # Common errors: message not found, message can't be deleted, etc.
        if "message to delete not found" in str(e) or "message can't be deleted" in str(e):
            logger.warning(f"Failed to delete message {message_id} in chat {chat_id}: {e} (Ignoring)")
        else:
            logger.error(f"Unexpected Telegram error deleting message {message_id} in chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Generic error deleting message {message_id} in chat {chat_id}: {e}") 