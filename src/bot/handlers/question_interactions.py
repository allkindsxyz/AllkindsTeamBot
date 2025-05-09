"""
Question interaction handlers - for answering, deleting, and skipping questions.
"""

from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from loguru import logger

from src.db.repositories import user_repo, question_repo, answer_repo
from src.db.models import AnswerType
from src.bot.states import QuestionFlow
from src.bot.utils.group_utils import can_delete_question
from src.bot.handlers.question_display import check_and_display_next_question

# Points for different actions
POINTS_FOR_ANSWERING = 1
POINTS_FOR_CREATING_QUESTION = 5

async def process_answer_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handles callback when user answers a question, saves to DB, shows selected answer."""
    
    try:
        # Parse the callback data
        callback_data = callback.data
        logger.info(f"Processing answer callback: {callback_data}")
        
        # Clean up any instruction or group info messages
        data = await state.get_data()
        group_info_msg_id = data.get("group_info_msg_id")
        instructions_msg_id = data.get("instructions_msg_id")
        
        if group_info_msg_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, group_info_msg_id)
                await state.update_data(group_info_msg_id=None)
            except Exception as e:
                logger.warning(f"Failed to delete group info message: {e}")
        
        if instructions_msg_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, instructions_msg_id)
                await state.update_data(instructions_msg_id=None)
            except Exception as e:
                logger.warning(f"Failed to delete instructions message: {e}")
        
        # Split by : to get parts
        parts = callback_data.split(":")
        if len(parts) < 3:
            logger.error(f"Invalid callback data format: {callback_data}")
            await callback.answer("Invalid callback data", show_alert=True)
            return
            
        _, question_id_str, answer_type_str = parts
        question_id = int(question_id_str)
        
        # Check if the question exists right away, before any processing
        question = await question_repo.get(session, question_id)
        if not question:
            logger.info(f"User {callback.from_user.id} tried to answer a deleted question {question_id}")
            await callback.answer("This question has been deleted.", show_alert=True)
            
            # Update the message to indicate the question is deleted
            deleted_text = "❌ This question has been deleted."
            try:
                await callback.message.edit_text(deleted_text, reply_markup=None)
                logger.info(f"Updated message to show question {question_id} was deleted")
            except Exception as e:
                logger.warning(f"Failed to update message for deleted question: {e}")
            
            return
        
        # Check if user is toggling the answer (clicked on the answer button)
        if answer_type_str == "toggle":
            logger.info(f"User {callback.from_user.id} toggling answer for question {question_id}")
                
            # Show all answer options
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="👎👎", callback_data=f"answer:{question_id}:{AnswerType.STRONG_NO.value}"),
                    types.InlineKeyboardButton(text="👎", callback_data=f"answer:{question_id}:{AnswerType.NO.value}"),
                    types.InlineKeyboardButton(text="⏭️", callback_data=f"skip_question:{question_id}"),
                    types.InlineKeyboardButton(text="👍", callback_data=f"answer:{question_id}:{AnswerType.YES.value}"),
                    types.InlineKeyboardButton(text="👍👍", callback_data=f"answer:{question_id}:{AnswerType.STRONG_YES.value}"),
                ]
            ])
            
            # Add delete button if user is the author
            user_tg = callback.from_user
            db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
            if db_user and question.author_id == db_user.id:
                # Add a second row with the delete button
                delete_button = [
                    types.InlineKeyboardButton(
                        text="🗑️ Delete",
                        callback_data=f"delete_question:{question.id}"
                    )
                ]
                
                # Get the current keyboard rows
                current_rows = keyboard.inline_keyboard
                # Add the delete button row
                current_rows.append(delete_button)
                # Create new keyboard with the additional row
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=current_rows)
                
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await state.update_data(is_showing_single_answer=False)
            await callback.answer("Choose a new answer")
            return

        # Process a new answer
        telegram_user_id = callback.from_user.id
        db_user = await user_repo.get_by_telegram_id(session, telegram_user_id)
        if not db_user:
            logger.error(f"User {telegram_user_id} not found in DB for answering.")
            await callback.answer("Error: Could not find your user account.", show_alert=True)
            return
        
        # Convert answer_type_str to enum value
        try:
            answer_type = AnswerType(answer_type_str)
            logger.info(f"User {db_user.id} selected answer {answer_type} for question {question_id}")
        except ValueError:
            logger.error(f"Invalid answer type: {answer_type_str}")
            await callback.answer("Invalid answer type", show_alert=True)
            return
        
        # Get current answer if exists
        try:
            existing_answer = await answer_repo.get_answer(session, db_user.id, question_id)
            
            # If exists, toggle answer value
            if existing_answer:
                # Update existing answer
                await answer_repo.save_answer(session, db_user.id, question_id, answer_type.value, answer_type.to_int())
                logger.info(f"Updated answer {existing_answer.id} for user {db_user.id}, question {question_id} to {answer_type}")
            else:
                # Create new answer
                new_answer = await answer_repo.save_answer(session, db_user.id, question_id, answer_type.value, answer_type.to_int())
                logger.info(f"Created new answer for user {db_user.id}, question {question_id}: {answer_type}")
                
                # Award points to the user for answering
                await user_repo.add_points(session, db_user.id, POINTS_FOR_ANSWERING)
                updated_user = await user_repo.get(session, db_user.id)
                logger.info(f"Awarded {POINTS_FOR_ANSWERING} points to user {db_user.id} for answering. New balance: {updated_user.points}")
        
        except Exception as e:
            logger.exception(f"Error processing answer: {e}")
            await callback.answer("An error occurred while processing your answer.", show_alert=True)
        
        # Change the displayed button to show only the selected answer
        selected_text = {
            AnswerType.STRONG_NO: "👎👎 Strong No",
            AnswerType.NO: "👎 No",
            AnswerType.YES: "👍 Yes",
            AnswerType.STRONG_YES: "👍👍 Strong Yes"
        }
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=selected_text[answer_type], callback_data=f"answer:{question_id}:toggle")]
        ])
        
        # Save state for this question interaction
        await state.update_data(
            is_showing_single_answer=True,
            last_answered_question_id=question_id,
            last_answered_msg_id=callback.message.message_id
        )
        
        # Update the message with the selected answer
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(f"Answer recorded: {selected_text[answer_type]}")
        
        # Show the next question
        group_id = data.get("current_group_id")
        if group_id:
            await check_and_display_next_question(callback.message, db_user, group_id, state, session)
        
    except Exception as e:
        logger.exception(f"Error processing answer: {e}")
        await callback.answer("An error occurred while processing your answer.", show_alert=True)


async def on_skip_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user skips a question."""
    try:
        await callback.answer("Question skipped")
        
        # Parse question ID from callback data
        question_id = int(callback.data.split(":")[1])
        
        # Get user from DB
        user_tg = callback.from_user
        db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if not db_user:
            logger.error(f"User {user_tg.id} not found in DB when skipping question.")
            await callback.message.edit_text("Error: Could not find your user account.")
            return
        
        # Delete current message to clean up
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete skipped question message: {e}")
        
        # Get data from state
        data = await state.get_data()
        group_id = data.get("current_group_id")
        
        if not group_id:
            logger.warning(f"No group ID found in state for user {db_user.id} during skip")
            await callback.message.answer("Error: Could not determine which group you're in.")
            return
        
        # Show the next question
        await check_and_display_next_question(callback.message, db_user, group_id, state, session)
        
    except Exception as e:
        logger.exception(f"Error skipping question: {e}")
        await callback.answer("An error occurred while skipping the question.", show_alert=True)


async def on_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user wants to delete a question."""
    await callback.answer("Delete this question?")
    
    # Parse question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Set state to confirming_delete
    await state.set_state(QuestionFlow.confirming_delete)
    await state.update_data(delete_question_id=question_id)
    
    # Get the question from the database
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    # Create keyboard with confirm/cancel buttons
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(
                text="✅ Delete",
                callback_data=f"confirm_delete_question:{question_id}"
            ),
            types.InlineKeyboardButton(
                text="❌ Cancel",
                callback_data=f"cancel_delete_question:{question_id}"
            ),
        ]
    ])
    
    # Show confirmation
    await callback.message.edit_text(
        text=f"Are you sure you want to delete this question?\n\n{question.text}",
        reply_markup=keyboard
    )


async def on_confirm_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle confirmation of question deletion."""
    await callback.answer("Deleting question...")
    
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.edit_text("Error: Could not find your user account.")
        return
    
    # Get the question
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    # Check if user can delete this question
    can_delete = await can_delete_question(db_user.id, question, session)
    if not can_delete:
        await callback.message.edit_text("You can only delete questions you created or as a team creator.")
        return
    
    # Delete the question
    await question_repo.mark_deleted(session, question_id)
    await session.commit()
        
    # Log the deletion
    is_author = question.author_id == db_user.id
    if is_author:
        logger.info(f"User {db_user.id} deleted their own question {question_id}")
    else:
        logger.info(f"User {db_user.id} as group creator deleted question {question_id} created by user {question.author_id}")
        
    # Delete the message instead of showing "Question deleted"
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message after question deletion: {e}")
    
    # Clear state
    await state.clear()
    
    # Get group ID and name from state data
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    # Set state back to viewing_question
    if group_id and group_name:
        await state.update_data(current_group_id=group_id, current_group_name=group_name)
        await state.set_state(QuestionFlow.viewing_question)


async def on_cancel_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """
    Handle cancellation of question deletion.
    Simply dismisses the confirmation dialog by deleting the message.
    """
    await callback.answer("Cancelled")
    
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get the original question from the database
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    # Get user
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.edit_text("Error: Could not find your user account.")
        return
    
    # Restore the original question display
    from src.bot.handlers.question_display import display_single_question
    await display_single_question(callback.message, question, db_user, session, state)
    
    # Reset state to viewing_question
    await state.set_state(QuestionFlow.viewing_question)


def register_handlers(dp: Dispatcher) -> None:
    """Register question interaction handlers."""
    # Register answer handlers
    dp.callback_query.register(process_answer_callback, F.data.startswith("answer:"))
    dp.callback_query.register(on_skip_question, F.data.startswith("skip_question:"))
    
    # Register delete handlers
    dp.callback_query.register(on_delete_question, F.data.startswith("delete_question:"))
    dp.callback_query.register(on_confirm_delete_question, F.data.startswith("confirm_delete_question:"))
    dp.callback_query.register(on_cancel_delete_question, F.data.startswith("cancel_delete_question:"))
    
    logger.info("Registered question interaction handlers") 