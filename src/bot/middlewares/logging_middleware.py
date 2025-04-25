from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Update, CallbackQuery
from aiogram.fsm.context import FSMContext
from loguru import logger

class StateLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Check if the event is a CallbackQuery
        if isinstance(event, CallbackQuery) and event.message:
            # Get the FSMContext from the data passed by Aiogram
            state: FSMContext = data.get('state')
            if state:
                current_state = await state.get_state()
                logger.info(f"CallbackQueryMiddleware: User {event.from_user.id} state is '{current_state}' for callback data '{event.data}'")
            else:
                logger.warning("CallbackQueryMiddleware: State context not found in data.")
        elif event.message: # Log state for regular messages too
             state: FSMContext = data.get('state')
             if state:
                current_state = await state.get_state()
                logger.info(f"MessageMiddleware: User {event.message.from_user.id} state is '{current_state}'")

        # Proceed with the next middleware/handler
        return await handler(event, data) 