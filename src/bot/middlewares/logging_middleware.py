from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Update, CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from loguru import logger

class StateLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Log detailed information about the update
        if hasattr(event, 'update_id'):
            logger.info(f"Processing update ID: {event.update_id}")

        # Handle callback queries with extra debugging
        if event.callback_query:
            user_id = event.callback_query.from_user.id
            callback_data = event.callback_query.data
            
            # Get the FSMContext
            state = data.get('state')
            current_state = "None"
            if state:
                current_state = await state.get_state() or "None"
            
            # Log detailed callback information
            logger.info(f"CALLBACK: User {user_id} | Data '{callback_data}' | State '{current_state}'")
            logger.debug(f"Callback full data: {event.callback_query.model_dump_json()}")
            
            # Get state data for more context
            if state:
                state_data = await state.get_data()
                if state_data:
                    logger.debug(f"User {user_id} state data: {state_data}")
                    
        # Handle regular messages
        elif event.message:
            user_id = event.message.from_user.id
            message_text = event.message.text or "[No text]"
            
            # Log message details
            logger.info(f"MESSAGE: User {user_id} | Text '{message_text[:30]}...' if len(message_text) > 30 else message_text")
            
            # Get the FSMContext
            state = data.get('state')
            if state:
                current_state = await state.get_state() or "None"
                logger.info(f"User {user_id} state is '{current_state}'")
                
                # Log state data
                state_data = await state.get_data()
                if state_data:
                    logger.debug(f"User {user_id} state data: {state_data}")

        try:
            # Proceed with the next middleware/handler
            return await handler(event, data)
        except Exception as e:
            # Log any exceptions in handler processing
            logger.error(f"Error processing update: {e}")
            # For callbacks, log the data that caused the error
            if event.callback_query:
                logger.error(f"Error occurred with callback data: {event.callback_query.data}")
            raise 