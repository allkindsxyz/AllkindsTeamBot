import logging
from typing import Optional

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import check_and_display_next_question, can_delete_question
from src.db.repositories.user import user_repo
from src.db.repositories.answer import answer_repo
from src.db.repositories.group import group_repo
from src.db.repositories.question import question_repo

logger = logging.getLogger(__name__)

async def reset_button_flag(message: types.Message, state: FSMContext) -> None:
    """Reset the answered_questions_loaded flag to ensure the button appears after bot restart."""
    if not state:
        logger.warning("No state provided to reset_button_flag")
        return
        
    user_id = message.from_user.id
    logger.info(f"DEBUG: Resetting answered_questions_loaded flag for user {user_id}")
    
    try:
        # Force reset the flag to ensure the button shows
        await state.update_data(answered_questions_loaded=False)
        logger.info(f"DEBUG: Successfully reset answered_questions_loaded flag for user {user_id}")
        
        # Clear any button message ID to ensure a fresh button is sent
        data = await state.get_data()
        if "load_answers_button_msg_id" in data:
            await state.update_data(load_answers_button_msg_id=None)
            logger.info(f"DEBUG: Cleared load_answers_button_msg_id for user {user_id}")
        
        # Clear any cached data related to answered questions
        if "has_answers_cache" in data:
            await state.update_data(has_answers_cache=None)
            logger.info(f"DEBUG: Cleared has_answers_cache for user {user_id}")
        
        logger.info(f"DEBUG: Button flag reset completed for user {user_id}")
    except Exception as e:
        logger.error(f"DEBUG: Error resetting answered_questions_loaded flag: {e}", exc_info=True)

async def check_has_answered_questions(user_id: int, group_id: int, session: AsyncSession) -> bool:
    """Check if a user has already answered questions in a group."""
    logger.info(f"DEBUG: Checking if user {user_id} has answered questions in group {group_id}")
    try:
        # Get user from DB
        db_user = await user_repo.get_by_telegram_id(session, user_id)
        if not db_user:
            logger.error(f"DEBUG: User {user_id} not found in DB when checking answered questions")
            return False
        
        logger.info(f"DEBUG: Found user in DB with ID {db_user.id}")

        # Get user's answers for this group
        answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
        answer_count = len(answers) if answers else 0
        logger.info(f"DEBUG: User {user_id} has {answer_count} answers in group {group_id}")
        
        # Log the first few answers for debugging
        if answers and len(answers) > 0:
            sample_answer = answers[0]
            logger.info(f"DEBUG: Sample answer - ID: {sample_answer.id}, Question ID: {sample_answer.question_id}, Type: {sample_answer.answer_type}")
        
        return bool(answers)
    except Exception as e:
        logger.error(f"DEBUG: Error checking for answered questions: {e}", exc_info=True)
        return False

async def show_load_answered_questions_button(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Show the 'Load answered questions' button if the user has answered questions."""
    user_id = message.from_user.id
    logger.info(f"=== DEBUG: show_load_answered_questions_button called for user {user_id} ===")
    
    # Get current group from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    logger.info(f"DEBUG: User state data: {data}")
    
    # Exit early if no group ID is available
    if not group_id:
        logger.warning(f"DEBUG: No group_id found in state for user {user_id} when showing load button")
        return
        
    # ALWAYS check if the user has answers, regardless of any state flags
    has_answers = await check_has_answered_questions(user_id, group_id, session)
    logger.info(f"DEBUG: User {user_id} has_answers = {has_answers}")
    
    if has_answers:
        # Create the inline keyboard for "Load answered questions" button
        logger.info(f"DEBUG: Creating 'Load answered questions' button for user {user_id}")
        try:
            # First check if we already sent a button in this session
            button_msg_id = data.get("load_answers_button_msg_id")
            if button_msg_id:
                # Try to delete the old button first to avoid duplicates
                try:
                    logger.info(f"DEBUG: Attempting to delete old button message with ID {button_msg_id}")
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=button_msg_id)
                    logger.info(f"DEBUG: Successfully deleted old button message")
                except Exception as e:
                    logger.warning(f"DEBUG: Failed to delete old button message: {e}")
            
            # Create a keyboard with a highly visible button - FIX: proper initialization
            button = InlineKeyboardButton(text="📋 Load answered questions", callback_data="load_answered_questions")
            inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[button]])
            
            # Send the button with explanatory text
            logger.info(f"DEBUG: Sending 'Load answered questions' button to user {user_id}")
            sent_msg = await message.answer("Click to see your answered questions:", reply_markup=inline_keyboard)
            logger.info(f"DEBUG: Sent button message with ID {sent_msg.message_id}")
            
            # Store the button message ID in state to manage it later
            await state.update_data(load_answers_button_msg_id=sent_msg.message_id)
        except Exception as e:
            logger.error(f"DEBUG: Error sending button: {e}", exc_info=True)
    else:
        logger.info(f"DEBUG: User {user_id} has no answered questions, not showing button")

async def on_load_answered_questions(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle the 'Load answered questions' button click."""
    # Log debugging info
    user_id = callback.from_user.id if callback.from_user else "Unknown"
    logger.info(f"DEBUG: on_load_answered_questions CALLED for user {user_id}")
    logger.info(f"DEBUG: callback data: {callback.data}")
    
    if state:
        current_state = await state.get_state()
        logger.info(f"DEBUG: Current state: {current_state}")
    
    await callback.answer("Loading your answered questions...")
    
    # Hide the button by deleting the message that contains it
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete 'Load answered questions' button: {e}")
    
    # Set flag in state to prevent showing the button again in this session
    await state.update_data(answered_questions_loaded=True)
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        logger.error(f"User {user_tg.id} not found in DB when loading answered questions")
        await callback.message.answer("Error: Could not find your user account. Please try /start again.")
        return
    
    # Get current group from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    if not group_id:
        logger.error(f"No group_id found in state for user {user_tg.id}")
        await callback.message.answer("Error: Could not determine your current group.")
        return
    
    # Get group info
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found in DB")
        await callback.message.answer("Error: Your team no longer exists.")
        return
    
    # Get user's answers for this group
    answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
    if not answers:
        await callback.message.answer("You haven't answered any questions in this team yet.")
        return
    
    logger.info(f"Found {len(answers)} answered questions for user {db_user.id} in group {group_id}")
    
    # Get the questions for these answers
    question_ids = [a.question_id for a in answers]
    questions = await question_repo.get_questions_by_ids(session, question_ids)
    
    # Create a map of question_id -> question for quick lookup
    question_map = {q.id: q for q in questions}
    
    # Create a map of question_id -> answer for quick lookup
    answer_map = {a.question_id: a for a in answers}
    
    # Send a message for each answered question
    sent_count = 0
    for question_id, answer in answer_map.items():
        # Skip if question no longer exists (was deleted)
        if question_id not in question_map:
            continue
            
        question = question_map[question_id]
        
        # Check if user can delete this question
        can_delete = await can_delete_question(db_user.id, question, session)
        
        # User has answered this question
        answer_display = "Unknown"
        if answer.answer_type == "skip":
            answer_display = "⏭️"
        else:
            emoji_map = {
                "strong_no": "👎👎", 
                "no": "👎", 
                "yes": "👍", 
                "strong_yes": "👍👍"
            }
            answer_display = emoji_map.get(answer.answer_type, answer.answer_type)
        
        # Question text
        question_text = question.text
        
        # Add action buttons
        keyboard_buttons = []
        # Answer button
        keyboard_buttons.append(
            types.InlineKeyboardButton(
                text=answer_display,
                callback_data=f"answer:{question.id}:toggle"
            )
        )
        
        # Delete button (for authors or group creators)
        if can_delete:
            keyboard_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question.id}"
                )
            )
        
        # Create the keyboard with the appropriate buttons
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
        
        # Send directly and get the sent message object
        await callback.message.answer(question_text, reply_markup=keyboard)
        sent_count += 1
        
        # Add a delay to avoid flood control
        import asyncio
        if sent_count % 5 == 0:
            await asyncio.sleep(0.5)
    
    logger.info(f"Displayed {sent_count} answered questions for user {db_user.id}")
    
    # After showing all answers, check and display the next question if available
    try:
        await check_and_display_next_question(callback.message, db_user, group_id, state, session)
    except Exception as e:
        logger.error(f"Error displaying next question after loading answers: {e}", exc_info=True)
        # Make sure we at least notify if there are no more questions
        await callback.message.answer("No more questions from people at the moment")

def register_handlers(dp):
    """Register handlers for load_answered_questions module."""
    # Define the needs_db flag
    needs_db = {"needs_db": True}
    
    # Import necessary components
    from src.bot.states import QuestionFlow
    from aiogram.filters import Command
    from aiogram import F
    
    # First, register a CATCH-ALL handler for the load_answered_questions button
    # This will catch all callbacks with this data, regardless of state or context
    dp.callback_query.register(
        on_load_answered_questions, 
        F.data == "load_answered_questions",
        flags=needs_db
    )
    
    # Register the specific state handlers as fallbacks
    dp.callback_query.register(
        on_load_answered_questions, 
        lambda c: c.data == "load_answered_questions", 
        QuestionFlow.viewing_question,
        flags=needs_db
    )
    
    # Add a debug log to see if this handler is being registered
    logger = logging.getLogger(__name__)
    logger.info("REGISTERED LOAD_ANSWERED_QUESTIONS HANDLER")
    
    # Register a handler to reset the answered_questions_loaded flag via hidden command
    dp.message.register(reset_button_flag, Command("reset_load_button"))
    
    # Register pre-processing middleware for /start commands to reset the flag
    dp.message.register(
        reset_button_flag, 
        F.text.startswith("/start"),
        flags={"cancelled_by_handler": False}
    ) 