from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import os
from loguru import logger
from src.core.diagnostics import track_command, IS_RAILWAY
from src.bot.states import QuestionFlow
from src.db.repositories import user_repo, group_repo, question_repo

# Points for creating questions
POINTS_FOR_CREATING_QUESTION = 5

logger = logging.getLogger(__name__)

@track_command
async def cmd_questions(message: types.Message) -> None:
    """Handle /questions command."""
    user = message.from_user
    logger.info(f"User {user.id} requested questions")
    
    # Enhanced error tracking for Railway
    if IS_RAILWAY:
        logger.info(f"RAILWAY: questions command called by user {user.id}")
        try:
            # TODO: Implement match fetching from database
            await message.answer("Questions feature coming soon! 🚀")
        except Exception as e:
            logger.error(f"RAILWAY ERROR in questions command: {str(e)}")
            # Send a user-friendly error message
            await message.answer("Sorry, there was an error processing your request. Please try again later.")
            raise
    else:
        # Original behavior for local development
        await message.answer("Questions feature coming soon! 🚀")


async def handle_direct_question_entry(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle direct question entry from user (a message that ends with a question mark)."""
    # Enhanced logging for debugging
    current_state = await state.get_state()
    logger.info(f"[QUESTION ENTRY] User {message.from_user.id} sent: '{message.text}'")
    logger.info(f"[QUESTION ENTRY] Current state: {current_state}")
    
    # Sanity check - ensure message ends with question mark
    if not message.text or not message.text.strip().endswith("?"):
        logger.warning(f"[QUESTION ENTRY] Message doesn't end with question mark: '{message.text}'")
        return
    
    # Add debugging for non-expected inputs
    menu_buttons = ["Find Match", "Team", "Instructions", "💬 Questions", "➕ Add Question", "🏠 Team", "❓ Help"]
    if message.text and message.text.strip() in menu_buttons:
        logger.warning(f"[CRITICAL] Menu button '{message.text}' treated as direct question! This should not happen.")
    
    if not session:
        logger.error("[QUESTION ENTRY] No database session provided")
        await message.reply("Error: Could not process your question. Please try again later.")
        return
    
    # Get current state data
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    logger.info(f"[QUESTION ENTRY] Retrieved from state: group_id={group_id}, group_name={group_name}")
    
    # If user is not in a group context, automatically find or create a group
    if not group_id or not group_name:
        logger.info(f"[QUESTION ENTRY] User {message.from_user.id} not in a group context, finding a group")
        
        # Get user from DB
        user_tg = message.from_user
        db_user, created = await user_repo.get_or_create_user(session, {
            "id": user_tg.id,
            "first_name": user_tg.first_name,
            "last_name": user_tg.last_name,
            "username": user_tg.username
        })
        
        logger.info(f"[QUESTION ENTRY] User DB lookup: id={db_user.id}, created={created}")
        
        # Check if user belongs to any groups
        user_groups = await group_repo.get_user_groups(session, db_user.id)
        
        if user_groups:
            # User already has groups, use the first one
            group = user_groups[0]
            group_id = group.id
            group_name = group.name
            logger.info(f"[QUESTION ENTRY] Auto-selected existing group {group_id} ({group_name})")
        else:
            # User has no groups, check for public groups
            public_groups = await group_repo.get_public_groups(session)
            
            if public_groups:
                # Join the first public group
                group = public_groups[0]
                await group_repo.add_user_to_group(session, db_user.id, group.id)
                group_id = group.id
                group_name = group.name
                logger.info(f"[QUESTION ENTRY] Added user to public group {group_id} ({group_name})")
            else:
                # Create a new public "General" group if none exists
                group = await group_repo.create_group(
                    session=session,
                    name="General",
                    description="Default group for all users",
                    created_by=db_user.id,
                    is_public=True
                )
                await group_repo.add_user_to_group(session, db_user.id, group.id)
                group_id = group.id
                group_name = group.name
                logger.info(f"[QUESTION ENTRY] Created new public group {group_id} ({group_name})")
        
        # Update state with the group context
        await state.update_data(current_group_id=group_id, current_group_name=group_name)
        logger.info(f"[QUESTION ENTRY] Updated state with group_id={group_id}, group_name={group_name}")
    
    # Set state for question creation
    await state.set_state(QuestionFlow.reviewing_question)
    question_text = message.text.strip()
    # Make sure the correct question text is stored in state
    await state.update_data(new_question_text=question_text)
    logger.info(f"[QUESTION ENTRY] Set state to reviewing_question, saved question: '{question_text}'")
    
    # For now, simplify the process without OpenAI validation
    # Simply store the question text and ask for confirmation
    confirmation_text = f"Your question:\n\n{question_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    
    try:
        confirmation_message = await message.reply(confirmation_text, reply_markup=keyboard)
        # Store message IDs for later cleanup
        await state.update_data(
            confirmation_message_id=confirmation_message.message_id,
            original_question_message_id=message.message_id
        )
        logger.info(f"[QUESTION ENTRY] Sent confirmation message (ID: {confirmation_message.message_id})")
    except Exception as e:
        logger.error(f"[QUESTION ENTRY] Error sending confirmation: {e}")
        # Try to recover by sending a different message
        await message.answer("There was an error processing your question. Please try again.")
        await state.set_state(QuestionFlow.viewing_question)


async def on_confirm_add_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle confirmation to add a new question."""
    logger.info(f"[CONFIRM QUESTION] User {callback.from_user.id} confirmed question")
    
    # Debug: log current state
    current_state = await state.get_state()
    data = await state.get_data()
    logger.info(f"[CONFIRM QUESTION] Current state: {current_state}")
    logger.info(f"[CONFIRM QUESTION] State data: {data}")
    
    if not session:
        logger.error("[CONFIRM QUESTION] No database session provided")
        await callback.answer("Error: Database connection issue. Please try again later.", show_alert=True)
        return
    
    # Acknowledge the callback to stop the loading indicator
    await callback.answer()
    
    # Get state data
    question_text = data.get("new_question_text")
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    logger.info(f"[CONFIRM QUESTION] Retrieved data: text='{question_text}', group_id={group_id}, group_name={group_name}")
    
    if not question_text or not group_id:
        logger.error(f"[CONFIRM QUESTION] Missing required data: question_text={question_text}, group_id={group_id}")
        await callback.message.edit_text("Error: Missing data. Please try asking your question again.")
        await state.set_state(QuestionFlow.viewing_question)
        return
    
    # Get user from DB
    db_user = await user_repo.get_by_telegram_id(session, callback.from_user.id)
    if not db_user:
        logger.error(f"[CONFIRM QUESTION] User {callback.from_user.id} not found in database")
        await callback.message.edit_text("Error: Your user profile could not be found. Please restart with /start.")
        await state.set_state(QuestionFlow.viewing_question)
        return
    
    try:
        # Create the question in database
        logger.info(f"[CONFIRM QUESTION] Creating question: '{question_text}' for group {group_id}")
        new_question = await question_repo.create_question(
            session=session,
            text=question_text,
            author_id=db_user.id,
            group_id=group_id,
            is_active=True
        )
        
        logger.info(f"[CONFIRM QUESTION] Question created with ID: {new_question.id}")
        
        # Award points to the user for creating a question
        await user_repo.add_points(session, db_user.id, POINTS_FOR_CREATING_QUESTION)
        updated_user = await user_repo.get(session, db_user.id)
        logger.info(f"[CONFIRM QUESTION] Awarded {POINTS_FOR_CREATING_QUESTION} points to user {db_user.id} for creating a question. New balance: {updated_user.points}")
        
        # Confirm to the user
        points_text = f"+{POINTS_FOR_CREATING_QUESTION} points! "
        success_text = f"✅ {points_text}Your question has been added to {group_name}!\n\nOther members will now see it when they interact with the bot."
        await callback.message.edit_text(success_text)
        
        # Reset state to allow more questions
        await state.set_state(QuestionFlow.viewing_question)
        
        # Clear state data related to this question
        await state.update_data(
            new_question_text=None,
            confirmation_message_id=None,
            original_question_message_id=None
        )
        
        # If there was a "no more questions" message shown, delete it
        no_questions_msg_id = data.get("no_questions_msg_id")
        no_questions_shown = data.get("no_questions_shown", False)
        
        if no_questions_msg_id and no_questions_shown:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=no_questions_msg_id
                )
                logger.info(f"[CONFIRM QUESTION] Deleted 'no more questions' message {no_questions_msg_id}")
                # Reset the flag and message ID
                await state.update_data(no_questions_shown=False, no_questions_msg_id=None)
            except Exception as e:
                logger.warning(f"[CONFIRM QUESTION] Failed to delete 'no more questions' message: {e}")
        
        # Display the question to the user so they can answer it
        from src.bot.handlers.question_display import display_single_question
        try:
            # Display the question with answer buttons
            await display_single_question(callback.message, new_question, db_user, session, state)
            logger.info(f"[CONFIRM QUESTION] Displayed question {new_question.id} to author")
        except Exception as display_error:
            logger.error(f"[CONFIRM QUESTION] Error displaying question: {display_error}")
            # Display a fallback message if there's an error showing the question
            await callback.message.answer("Your question has been saved. You can view and answer it later.")
            
    except Exception as e:
        logger.error(f"[CONFIRM QUESTION] Error adding question to database: {e}")
        await callback.message.edit_text("Sorry, there was an error adding your question. Please try again later.")
        # Ensure state is reset even on error
        await state.set_state(QuestionFlow.viewing_question)


async def on_cancel_add_question(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle cancellation of adding a new question."""
    logger.info(f"[CANCEL QUESTION] User {callback.from_user.id} cancelled question")
    
    # Debug current state
    current_state = await state.get_state()
    data = await state.get_data()
    logger.info(f"[CANCEL QUESTION] Current state: {current_state}")
    logger.info(f"[CANCEL QUESTION] State data: {data}")
    
    # Acknowledge the callback to stop the loading indicator
    await callback.answer("Question cancelled")
    
    # Get message IDs from state data
    confirmation_message_id = data.get("confirmation_message_id")
    original_question_message_id = data.get("original_question_message_id")
    
    logger.info(f"[CANCEL QUESTION] Message IDs: confirmation={confirmation_message_id}, original={original_question_message_id}")
    
    # Clean up messages
    cleanup_successful = True
    try:
        # Delete the confirmation message
        if callback.message:
            await callback.message.delete()
            logger.info("[CANCEL QUESTION] Deleted confirmation message")
        
        # Delete the original question message
        if original_question_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=original_question_message_id
                )
                logger.info(f"[CANCEL QUESTION] Deleted original message {original_question_message_id}")
            except Exception as e:
                logger.warning(f"[CANCEL QUESTION] Failed to delete original message: {e}")
                cleanup_successful = False
    except Exception as e:
        logger.warning(f"[CANCEL QUESTION] Error cleaning up messages: {e}")
        cleanup_successful = False
        # If we can't delete the messages, just update the confirmation message
        try:
            await callback.message.edit_text("❌ Question cancelled.")
            logger.info("[CANCEL QUESTION] Updated message to show cancellation")
        except Exception as edit_error:
            logger.warning(f"[CANCEL QUESTION] Failed to edit message: {edit_error}")
    
    # Reset state to allow more questions - IMPORTANT!
    await state.set_state(QuestionFlow.viewing_question)
    logger.info("[CANCEL QUESTION] Reset state to viewing_question")
    
    # Clear state data related to this question to prevent issues with future questions
    await state.update_data(
        new_question_text=None,
        confirmation_message_id=None,
        original_question_message_id=None
    )
    logger.info("[CANCEL QUESTION] Cleared question data from state")
    
    # Let the user know they can ask another question if cleanup failed
    if not cleanup_successful:
        try:
            await callback.message.answer("You can now ask another question if you wish.")
            logger.info("[CANCEL QUESTION] Sent follow-up message due to incomplete cleanup")
        except Exception as answer_error:
            logger.warning(f"[CANCEL QUESTION] Failed to send follow-up message: {answer_error}")


def register_handlers(dp: Dispatcher) -> None:
    """Register question-related handlers."""
    # Register the /questions command
    dp.message.register(cmd_questions, Command("questions"))
    
    # Register the direct question entry handler - CRITICAL SECTION
    # This will catch any message that ends with a question mark (?) and isn't a menu button
    menu_buttons = ['Find Match', 'Team', 'Instructions', '💬 Questions', '✨ Who vibes with you most now?', 
                   '➕ Add Question', '🏠 Team', '❓ Help', '❓ Instructions']
    
    # Use explicit lambda function with all safety checks
    # First, define our filter function for better debugging
    def question_filter(message):
        if not message.text:
            return False
        
        text = message.text.strip()
        ends_with_question = text.endswith("?")
        is_button = text in menu_buttons
        
        logger.info(f"[FILTER] Message: '{text}' | Ends with ?: {ends_with_question} | Is button: {is_button}")
        
        # Only returns True if it ends with ? and is not a button
        return ends_with_question and not is_button
    
    # Register with our custom filter
    dp.message.register(
        handle_direct_question_entry, 
        question_filter
    )
    
    logger.info("Registered direct question entry handler with enhanced safety checks and logging")
    
    # Register the callback handlers for question confirmation/cancellation
    dp.callback_query.register(on_confirm_add_question, F.data == "confirm_add_question")
    dp.callback_query.register(on_cancel_add_question, F.data == "cancel_add_question")
    
    logger.info("Registered question confirmation/cancellation handlers") 